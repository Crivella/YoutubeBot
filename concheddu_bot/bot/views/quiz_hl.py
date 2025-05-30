import random
from typing import Awaitable

import discord

from ... import models as m
from ...models.quiz_hl import object_type_map
from .. import get_current_bot
from ..utils import ensure_response, ensure_user, safe_response
from .buttons import CallbackButton
from .utils import elide, logger

NONE_STR = '__NO__NE__'

async def get_object_thumbnail(obj):
    """Get the thumbnail for an object"""
    try:
        res = await obj.get_thumbnail()
    except Exception as e:
        logger.error(f'Error getting thumbnail for {obj}: {e}')
        res = None
    return res

class QuizHighLowRunner(discord.ui.View):
    def __init__(
            self,
            itc: discord.Interaction,
            object_type: str,
            object_param: str,
            max_top: int,
            user: discord.Member | None = None,
        ):
        super().__init__()
        self.itc = itc
        self.bot = get_current_bot()
        self.orig_channel = self.channel = itc.channel
        self.quiz_obj: m.QuizHighLow = None
        self.object_map: dict = {}

        self.object_type = object_type
        self.object_param = object_param
        self.max_top = max_top

        self.start = CallbackButton(
            label='Start Quiz',
            style=discord.ButtonStyle.primary
        )

        self.start.add_callback(self.submit_quiz)

        self.add_item(self.start)

        self.objects: list = None
        self.object_score_map: dict[int, int] = {}

        self.idx = 0
        self.id1 = 0  # Id for the first object
        self.id2 = 0  # Id for the second object


        self.score: dict[int, int] = {}
        self.answers: list[bool] = []

        self.play_view = discord.ui.View()
        self.play_message: discord.Message = None

        self.player: discord.Member = user
        self.user: m.DiscordUser = None
        self.server: m.DiscordServer = None

        self.scoreboard: discord.Message = None

        self.on_start: list[Awaitable] = []
        self.on_finish: list[Awaitable] = []

    @ensure_response(before=False, defer=True)
    async def submit_quiz(self, itc: discord.Interaction):
        """Start a quiz: select atleast one user and a playlist to choose songs from.
        if no playlist is selected, the songs will be picked from all the songs in the server.

        Args:
            itc (discord.Interaction): Interaction
            num_songs (int, optional): The number of songs to pick from the playlist. Defaults to 20.
        """
        object_cls = object_type_map.get(self.object_type, None)
        if object_cls is None:
            await safe_response(itc, f'Invalid object type: {self.object_type}', ephemeral=True, delete_after=10)
            return

        q = object_cls.objects
        if self.max_top > 0:
            q = q.order_by(f'-{self.object_param}')  # order by the object parameter in descending order
            q = q[:self.max_top] # limit to max_top objects
        else:
            q = q.order_by('?')
            q = q[:100]  # limit to 3000 objects to avoid performance issues
        objects = [o async for o in q.all()]
        random.shuffle(objects)
        objects = objects[:100]
        if not objects:
            await safe_response(itc, f'No {self.object_type} found', ephemeral=True, delete_after=10)
            return

        for obj in objects:
            score = getattr(obj, self.object_param, None)
            if score is None:
                await safe_response(itc, f'Not all found objects have the parameter {self.object_param}', ephemeral=True, delete_after=10)
                return
            self.object_score_map[obj.id] = score

        self.object_map = {obj.id: obj for obj in objects}
        self.objects = [o.id for o in objects]

        logger.info(f'Found {len(objects)} objects of type {self.object_type} with parameter {self.object_param}')

        self.score = {self.player.id: 0}

        self.user = await m.DiscordUser.from_discord_user(self.player)
        self.server = server = await m.DiscordServer.from_discord_guild(itc.guild)

        self.quiz_obj = await m.QuizHighLow.objects.acreate(
            object_type=self.object_type,
            object_param=self.object_param,
            num_objects=len(objects),
            max_top=self.max_top,

            player=self.user,
            server=server,

            object_choice_ids=self.objects,
        )

        for callback in self.on_start:
            await callback(self.quiz_obj)

        self.id2 = self.objects[0]
        self.idx = 1
        self.channel = itc.channel

        embed = discord.Embed(
            title='Quiz started',
            color=0x00ff00
        )
        self.embed_details(embed)
        await self.itc.delete_original_response()
        await self.channel.send(embed=embed)
        await self.quiz_step()

    async def quiz_step(self):
        """Start a new quiz step"""
        if self.idx >= len(self.objects):
            return await self.quiz_finish()

        self.play_view.clear_items()

        self.id1 = self.id2
        self.id2 = self.objects[self.idx]

        self.higher_btn = CallbackButton(
            label='HIGHER ⬆️',
            style=discord.ButtonStyle.success,
            custom_id='quiz_hl_higher'
        )
        self.lower_btn = CallbackButton(
            label='LOWER ⬇️',
            style=discord.ButtonStyle.danger,
            custom_id='quiz_hl_lower'
        )

        async def process_guess(correct: bool):
            """Process the guess and update the score"""
            if not correct:
                await self.quiz_finish()
            else:
                self.score[self.player.id] += 1
                self.idx += 1
                await self.quiz_step()

        @ensure_response(before=False, defer=True)
        @ensure_user(users=[self.player], defer=True)
        async def high_guess(itc: discord.Interaction):
            """Guess that the first object has a higher score"""
            correct = await self.quiz_obj.guess(
                id1=self.id1,
                id2=self.id2,
                guess_direction=1,
                user=self.user
            )
            await process_guess(correct)

        @ensure_response(before=False, defer=True)
        @ensure_user(users=[self.player], defer=True)
        async def low_guess(itc: discord.Interaction):
            """Guess that the first object has a lower score"""
            correct = await self.quiz_obj.guess(
                id1=self.id1,
                id2=self.id2,
                guess_direction=-1,
                user=self.user
            )
            await process_guess(correct)

        self.higher_btn.add_callback(high_guess)
        self.lower_btn.add_callback(low_guess)

        view = discord.ui.View()
        view.add_item(self.higher_btn)
        view.add_item(self.lower_btn)
        self.play_view = view

        await self.step_message(view=view)

    async def step_message(self, view=None, reveal_last=False):
        """Generate/update the message for the current quiz step"""
        item1 = self.object_map[self.id1]
        item2 = self.object_map[self.id2]

        thumb1 = await get_object_thumbnail(item1)
        thumb2 = await get_object_thumbnail(item2)

        title1 = await item1.get_str()
        title2 = await item2.get_str()

        embed_score = discord.Embed(
            title='Current score',
            color=0x0000ff
        )
        embed1 = discord.Embed(
            title=f'{title1}: {self.object_score_map[item1.id]}',
            color=0x00ff00
        )
        score = self.object_score_map[item2.id] if reveal_last else '???'
        embed2 = discord.Embed(
            title=f'{title2}: {score}',
            color=0xff0000
        )

        self.embed_score(embed_score)

        files = []
        if thumb1:
            attach_name = f'{item1.id}_thumb.png'
            file = discord.File(await thumb1.get_image(), filename=attach_name)
            files.append(file)
            embed1.set_thumbnail(url=f'attachment://{attach_name}')
        if thumb2:
            attach_name = f'{item2.id}_thumb.png'
            file = discord.File(await thumb2.get_image(), filename=attach_name)
            files.append(file)
            embed2.set_thumbnail(url=f'attachment://{attach_name}')

        kwargs = {
            'content': f'Quiz step {self.idx} - Guess the score of the second object compared to the first one!',
            'embeds': [embed_score, embed1, embed2],
            'files': files,
            'view': view
        }

        if self.play_message is None:
            logger.debug(f'Sending new play message for quiz {self.quiz_obj.id}')
            self.play_message = await self.channel.send(**kwargs)
        else:
            kwargs['attachments'] = kwargs.pop('files', [])
            await self.play_message.edit(**kwargs)

    async def quiz_finish(self):
        """Finish the quiz"""
        await self.step_message(reveal_last=True)
        logger.info(f'Finishing quiz {self.quiz_obj.id} with {self.idx - 1} correct answers')
        await self.quiz_obj.finish()

        embed = discord.Embed(
            title='Quiz finished',
            color=0x00ff00
        )
        self.embed_details(embed)
        self.embed_score(embed)
        await self.orig_channel.send(embed=embed)

        for callback in self.on_finish:
            await callback()
        await safe_response(self.itc, 'Quiz finished!!!')

    def quiz_header(self) -> list[str]:
        """Return the quiz header

        Returns:
            list[str]: List of strings
        """
        return [
            f'- Object type: {self.object_type}',
            f'- Object parameter: {self.object_param}',
            f'- Number of objects: {len(self.objects)}',
            f'- Max top: {self.max_top}' if self.max_top > 0 else '- Random order',
            f'- Started by: {self.player.name}',
        ]

    def embed_details(self, embed: discord.Embed):
        msg = self.quiz_header()
        embed.add_field(
            name='Quiz details',
            value='\n'.join(msg),
            inline=False
        )

    def embed_score(self, embed: discord.Embed):
        """Embed the score in the given embed

        Args:
            embed (discord.Embed): The embed to add the score to
        """
        embed.add_field(name='Score', value=f'- {self.player.name}: {self.score[self.player.id]} points', inline=False)

    async def on_timeout(self):
        try:
            await self.itc.delete_original_response()
        except discord.NotFound:
            pass
