import asyncio
import random
from collections import defaultdict
from typing import Awaitable

import discord

from .... import models as m
from ....models.quiz_hl import object_type_map
from ... import get_current_bot
from ...buttons import CallbackButton
from ...utils import ensure_response, ensure_user, safe_response
from ..paged import AnimeCollectionOption, ListMultiSelect
from ..utils import elide, logger
from .utils import UserList, get_object_thumbnail

QUIZ_LIMIT = 200

class QuizHighLowRunner(discord.ui.View):
    """Quiz runner for high/low quiz game"""
    CHANNEL_PREFIX = 'quiz-hl'

    def __init__(
            self,
            itc: discord.Interaction,
            object_type: str,
            object_param: str,
            max_top: int,
            max_failures: int = 3,
            # user: discord.Member | None = None,
            collections: list[m.AnimeCollection] = None,
        ):
        super().__init__()
        self.itc = itc
        self.bot = get_current_bot()
        self.orig_channel = self.channel = itc.channel
        self.quiz_obj: m.QuizHighLow = None
        self.object_map: dict = {}
        self.max_failures = max_failures

        self.object_type = object_type
        self.object_param = object_param
        self.max_top = max_top

        users = self.itc.user.voice.channel.members

        self.select_users = UserList(users, min_values=1, max_values=len(users))
        collections = collections or []
        self.select_collections = ListMultiSelect(
            AnimeCollectionOption,
            collections,
            view=self
        )
        self.start = CallbackButton(
            label='Start Quiz',
            style=discord.ButtonStyle.primary
        )

        self.start.add_callback(self.submit_quiz)

        self.add_item(self.select_users)
        self.add_item(self.select_collections)
        self.add_item(self.start)

        self.objects: list = None
        self.object_score_map: dict[int, int] = {}

        self.idx = 0
        self.offset = 0  # Offset for the current user to account eliminated users
        self.id1 = 0  # Id for the first object
        self.id2 = 0  # Id for the second object

        self.creator: m.DiscordUser = None
        self.lives: dict[int, int] = {}
        self.score: dict[int, int] = {}
        self.answers: list[bool] = []
        self.user_answers: dict[int, list[bool]] = defaultdict(list)

        self.play_view = discord.ui.View()
        self.play_message: discord.Message = None

        # self.player: discord.Member = user
        self.users: list[discord.Member] = []
        self.alive_users: list[discord.Member] = []
        self.user_map: dict[int, m.DiscordUser] = {}
        self.user_collections: dict[int, m.AnimeCollection] = defaultdict(discord.Color.random)
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
        self.users = users = self.select_users.get_users()
        self.alive_users = users.copy()
        self.lives = {user.id: self.max_failures for user in users}
        for user in users:
            user_obj = await m.DiscordUser.from_discord_user(user)
            self.user_map[user.id] = user_obj
        self.score = {user.id: 0 for user in users}
        random.shuffle(users)

        if not users:
            await safe_response(itc, 'No users selected', ephemeral=True, delete_after=10)
            return

        object_cls = object_type_map.get(self.object_type, None)
        if object_cls is None:
            await safe_response(itc, f'Invalid object type: {self.object_type}', ephemeral=True, delete_after=10)
            return

        collections = self.select_collections.get_objects()

        q = object_cls.objects
        # Filter objects that do not have the required parameter
        q = q.exclude(**{f'{self.object_param}__isnull': True})

        if collections:
            collection_ids = [c.id for c in collections]
            if self.object_type == 'anime_character':
                # For characters, we need to filter by collection
                q = q.filter(animes__collections__id__in=collection_ids)
            elif self.object_type == 'anime':
                # For other object types, we can filter directly by collection
                q = q.filter(collections__id__in=collection_ids)
            else:
                raise ValueError(f'Unsupported object type: {self.object_type}')
            q = q.distinct()  # Ensure unique objects

        if self.max_top > 0:
            q = q.order_by(f'-{self.object_param}')  # order by the object parameter in descending order
            q = q[:self.max_top] # limit to max_top objects
        else:
            q = q.order_by('?')
            q = q[:QUIZ_LIMIT]  # limit to 3000 objects to avoid performance issues
        objects = [o async for o in q.all()]
        random.shuffle(objects)
        objects = objects[:QUIZ_LIMIT]
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

        # self.score = {self.player.id: 0}

        # self.user = await m.DiscordUser.from_discord_user(self.player)
        self.creator = await m.DiscordUser.from_discord_user(itc.user)
        self.server = await m.DiscordServer.from_discord_guild(itc.guild)

        self.quiz_obj = await m.QuizHighLow.objects.acreate(
            object_type=self.object_type,
            object_param=self.object_param,
            num_objects=len(objects),
            max_top=self.max_top,
            max_failures=self.max_failures,

            # player=self.user,
            creator=self.creator,
            server=self.server,

            object_choice_ids=self.objects,
        )

        for user in self.users:
            user = await m.DiscordUser.from_discord_user(user)
            await self.quiz_obj.players.aadd(user)
        if collections:
            await self.quiz_obj.collections.aadd(*collections)

        for callback in self.on_start:
            await callback(self.quiz_obj)


        # Create a new text channel and add only the users that are participating in the quiz
        new_channel = await itc.guild.create_text_channel(
            name=f'{self.CHANNEL_PREFIX}-{self.quiz_obj.id}',
            category=itc.channel.category,
            overwrites={
                itc.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                **{user: discord.PermissionOverwrite(read_messages=True) for user in users},
                self.bot.user: discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    embed_links=True,
                    attach_files=True,
                    manage_channels=True,
                    # https://github.com/discord/discord-api-docs/issues/2520
                    # manage_permissions=True,
                )
            }
        )
        self.channel = new_channel

        self.id2 = self.objects[0]
        self.idx = 1
        # self.channel = itc.channel

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

        user = self.alive_users.pop(0)
        user_obj = self.user_map[user.id]
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
            self.answers.append(correct)
            self.user_answers[user.id].append(correct)
            if not correct:
                self.lives[user.id] -= 1
            else:
                self.score[user.id] += 1
            if self.lives[user.id] > 0:
                self.alive_users.append(user)
            else:
                logger.info(f'User {user.name} has no lives left in quiz {self.quiz_obj.id}')
                if len(self.alive_users) <= 0:
                    await self.quiz_finish()
                    return
            self.idx += 1
            await self.quiz_step()

        @ensure_response(before=False, defer=True)
        @ensure_user(users=[user], defer=True)
        async def high_guess(itc: discord.Interaction):
            """Guess that the first object has a higher score"""
            correct = await self.quiz_obj.guess(
                id1=self.id1,
                id2=self.id2,
                guess_direction=1,
                user=user_obj
            )
            await process_guess(correct)

        @ensure_response(before=False, defer=True)
        @ensure_user(users=[user], defer=True)
        async def low_guess(itc: discord.Interaction):
            """Guess that the first object has a lower score"""
            correct = await self.quiz_obj.guess(
                id1=self.id1,
                id2=self.id2,
                guess_direction=-1,
                user=user_obj
            )
            await process_guess(correct)

        self.higher_btn.add_callback(high_guess)
        self.lower_btn.add_callback(low_guess)

        view = discord.ui.View()
        view.add_item(self.higher_btn)
        view.add_item(self.lower_btn)
        self.play_view = view

        await self.step_message(view=view, user=user)

    async def step_message(self, view=None, user=None, reveal_last=False):
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

        if user is not None:
            kwargs['allowed_mentions'] = discord.AllowedMentions(users=[user])
            kwargs['content'] = f'{user.mention} {kwargs["content"]}'

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

        if self.channel is not None and self.orig_channel != self.channel and self.channel.name.startswith(self.CHANNEL_PREFIX):
            try:
                await asyncio.sleep(10)
                await self.channel.delete()
            except discord.Forbidden:
                logger.warning(f'Could not delete channel {self.channel.name}, missing permissions')
            except discord.NotFound:
                logger.warning(f'Channel {self.channel.name} not found, already deleted?')
            self.channel = self.orig_channel

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
            f'- Max failures: {self.max_failures}',
            f'- Started by: {self.creator.username}',
        ]

    def embed_details(self, embed: discord.Embed):
        msg = self.quiz_header()
        embed.add_field(
            name='Quiz details',
            value='\n'.join(msg),
            inline=False
        )

    def embed_score(self, embed: discord.Embed, sort: bool = True):
        """Embed the score in the given embed

        Args:
            embed (discord.Embed): The embed to add the score to
        """
        if sort:
            lst = sorted(self.users, key=lambda user: self.score[user.id])[::-1]
        else:
            lst = self.users

        emoji_map = {
            None: '❔',
            False: '❌',
            True: '✅',
            1: '✅',
            0: '❌',
        }
        for user in lst:
            val = ''
            for ans in self.user_answers[user.id]:
                val += emoji_map[ans]
            lives = '❤️' * self.lives[user.id] if self.lives[user.id] > 0 else '💀'
            embed.add_field(
                name=f'{user.name} [{self.score[user.id]} points] ({lives})',
                value=val,
                inline=True
            )
        # embed.add_field(name='Score', value=f'- {self.player.name}: {self.score[self.player.id]} points', inline=False)

    async def on_timeout(self):
        try:
            await self.itc.delete_original_response()
        except discord.NotFound:
            pass
