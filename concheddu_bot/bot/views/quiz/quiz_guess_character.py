import random
from collections import defaultdict
from typing import Awaitable

import discord

from .... import models as m
from ... import get_current_bot
from ...utils import ensure_response, ensure_user, safe_response
from ..buttons import CallbackButton
from ..utils import elide, logger
from .utils import UserList, get_object_thumbnail

skip_titles = [
    'Minkia suko',
    'Shame!!',
    'Ram\'s lover',
    'Concheddu',
    'Is callonis',
    'WTF is this?',
]

NONE_STR = '__NO__NE__'


class QuizGuessCharacterRunner(discord.ui.View):
    CHANNEL_PREFIX = 'quiz-animechar'
    def __init__(
            self,
            itc: discord.Interaction,
            num_items: int = 5,
            max_top: int = 1000,
            max_choices: int = 1000
        ):
        super().__init__()
        self.itc = itc
        self.bot = get_current_bot()
        self.orig_channel = self.channel = itc.channel
        self.num_items = num_items
        self.max_top = max_top
        self.max_choices = max_choices

        users = self.itc.user.voice.channel.members

        self.select_users = UserList(users, min_values=1, max_values=len(users))
        self.start = CallbackButton(
            label='Start Quiz',
            style=discord.ButtonStyle.primary
        )

        self.start.add_callback(self.submit_quiz)

        self.add_item(self.select_users)
        self.add_item(self.start)

        self.idx = 0
        self.users: list[discord.Member] = []
        self.user_map: dict[int, discord.Member] = {}
        self.user_colors: dict[int, discord.Color] = defaultdict(discord.Color.random)
        self.characters: list = [m.AnimeCharacter]
        self.score: dict[int, int] = {}
        self.answers: list[bool] = []
        self.user_answers: dict[int, list[bool]] = defaultdict(list)

        self.scoreboard: discord.Message = None

        self.answer_callback = None

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

        users = self.select_users.get_users()
        random.shuffle(users)  #random order for the users

        if not users:
            await safe_response(itc, 'Select at least one user', ephemeral=True, delete_after=10)
            return

        q = m.AnimeCharacter.objects.get_queryset()
        q.order_by('-favorites')
        if self.max_top > 0:
            q = q[:self.max_top]

        characters = [c async for c in q.all()]

        needed = len(users) * self.num_items
        found = len(characters)
        if found < needed:
            await safe_response(
                itc, f'Not enough characters found ({found}/{needed})',
                ephemeral=True, delete_after=10
            )
            return
        logger.info(f'Found {found} items')

        if self.max_choices == 0:
            self.max_choices = len(characters)
            self.all_characters = characters
        else:
            self.max_choices = min(self.max_choices, len(characters))
            self.all_characters = random.sample(characters, self.max_choices)
        self.characters = random.sample(self.all_characters, needed)

        self.users = users
        self.user_map = {user.id: user for user in users}
        self.score = {user.id: 0 for user in users}
        logger.info('Quiz users:')
        for user in users:
            logger.info(f'  - {user.name}')
        logger.info('Quiz characters:')
        for char in self.characters:
            logger.info(f' - {char.name}')

        self.server = server = await m.DiscordServer.from_discord_guild(itc.guild)
        creator = await m.DiscordUser.from_discord_user(itc.user)
        await server.player.lock()
        self.quiz_obj = await m.QuizAnimeCharacter.objects.acreate(
            server=server,
            creator=creator,

            num_objects=len(self.characters),
            max_top=self.max_top,
            max_choices=self.max_choices,

            object_choice_ids=[char.id for char in self.characters],
        )
        for user in users:
            await self.quiz_obj.players.aadd(await m.DiscordUser.from_discord_user(user))

        for callback in self.on_start:
            await callback(self.characters, self.all_characters, self.quiz_obj)

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

        embed = discord.Embed(
            title='Quiz started',
            color=0x00ff00
        )
        self.embed_details(embed)
        await self.itc.delete_original_response()
        await self.channel.send(embed=embed)
        await self.display_score()
        await self.quiz_step()

    async def quiz_step(self):
        if self.idx >= len(self.characters):
            await self.quiz_finish()
            return

        user = self.users[self.idx % len(self.users)]
        chara = self.characters[self.idx]
        anime = None

        view = discord.ui.View()

        # server = self.server
        message = None
        answered = False

        self.answer_btn = CallbackButton(
            label=random.choice(skip_titles),
            style=discord.ButtonStyle.primary
        )

        @ensure_response(before=False, defer=True)
        @ensure_user(users=[user], defer=True)
        async def answer_callback(
            itc: discord.Interaction,
            answer_anime: m.AnimeObj = None,
            answer_character: m.AnimeCharacter = None,
            ):
            nonlocal message, answered
            if answered:
                return

            answered = True

            user_obj = await m.DiscordUser.from_discord_user(user)
            res_chara, res_anime = await self.quiz_obj.guess(
                real=chara,
                user=user_obj,
                guessed_char=answer_character,
                guessed_anime=answer_anime
                )

            msg = []
            result = res_chara or res_anime
            point_value = 0
            if res_chara:
                point_value += 2
                msg.append(f'- Correct character: {chara.name} ❤️❤️')
            else:
                answered_name = answer_character.name if answer_character else 'NONE'
                msg.append(f'- Incorrect character: {chara.name} 🙁🙁. You said {answered_name}')
            # if res_anime:
            #     point_value += 1
            #     msg.append(f'- Correct anime: {chara.anime.title} ❤️❤️')
            # else:
            #     msg.append(f'- Incorrect anime: {chara.anime.title} 🙁🙁')

            embed = discord.Embed(
                title= f'{user.nick}: ',
                description='\n'.join(msg),
                color=self.user_colors[user.id]
            )

            self.answers.append(result)
            app = 0
            if result:
                app = point_value
                self.score[user.id] += point_value
            answer = answer_character or answer_anime
            self.user_answers[user.id].append(app if answer is not None else None)

            view.clear_items()
            await message.edit(
                embed=embed,
                view=None,
                # attachments=attach,
                )
            await self.display_score()
            self.idx += 1
            await self.quiz_step()

        self.answer_btn.add_callback(answer_callback)
        self.answer_callback = answer_callback

        view.add_item(self.answer_btn)
        msg = f'<@{user.id}> \'s turn'

        embed_thumb = discord.Embed(
            title=f'Guess the character',
            color=self.user_colors[user.id]
        )
        thumb = await get_object_thumbnail(chara)
        if thumb:
            attach_name = f'char-{chara.mal_id}.png'
            file = discord.File(await thumb.get_image(), filename=attach_name)
            embed_thumb.set_image(url=f'attachment://{attach_name}')

        message = await self.channel.send(
            content=msg, view=view,
            embed=embed_thumb, file=file
        )

    async def command_answer(self, itc: discord.Interaction, anime: m.AnimeObj = None, chara: m.AnimeCharacter = None):
        """Command to answer the quiz"""
        if self.answer_callback:
            await self.answer_callback(itc, anime, chara)

    async def quiz_finish(self):
        """Finish the quiz"""
        await self.quiz_obj.finish()
        max_score = max(self.score.values())
        winners = [user for user in self.users if self.score[user.id] == max_score]
        msg = []
        if len(winners) == 1:

            msg.append(f'{winners[0].name} wins with {max_score} points')
        else:
            msg.append(f'Tie with {max_score} points between:')
            for user in winners:
                msg.append(f'  - {user.name}')

        embed = discord.Embed(
            title='Quiz finished',
            description=f'{sum(self.answers)} / {len(self.answers)} correct answers',
            color=0x00ff00
        )
        self.embed_details(embed)
        self.embed_score(embed, sort=True)
        await self.orig_channel.send(embed=embed)

        if self.channel is not None and self.orig_channel != self.channel and self.channel.name.startswith(self.CHANNEL_PREFIX):
            try:
                await self.channel.delete()
            except discord.Forbidden:
                logger.warning(f'Could not delete channel {self.channel.name}, missing permissions')
            except discord.NotFound:
                logger.warning(f'Channel {self.channel.name} not found, already deleted?')
            self.channel = self.orig_channel

        for callback in self.on_finish:
            await callback()
        await safe_response(self.itc, 'Quiz finished!!!')
        # await self.itc.delete_original_response()

    def quiz_header(self) -> list[str]:
        # TODO
        """Return the quiz header

        Returns:
            list[str]: List of strings
        """
        return [
            f'Quiz started by {self.itc.user.name}',
            f'- Choosing from {self.max_top} characters',
            f'- Each user will have to guess {self.num_items} characters',
            f'- Each character will have {self.max_choices} choices',
            # f'- Each user will have to guess {self.num_songs} songs',
            # f'- Each song will have {self.nmc} choices',
            # f'- Segment length: {self.segment_length} s',
            # f'- Segment mode: {self.segment_mode}',
            # f'- Audio filter: "{self.audio_filter}"',
            # f'- Multiple choice: {self.multiple_choice}',
            # f'- Show thumbnail: {self.show_thumbnail} (blur={self.thumbnail_blur})',
            # f'- Progressive: {self.progressive}',
        ]

    def embed_details(self, embed: discord.Embed):
        msg = self.quiz_header()
        embed.add_field(
            name='Quiz details',
            value='\n'.join(msg),
            inline=False
        )

    def embed_score(self, embed: discord.Embed, sort: bool = True):
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
            # number emojis
            2: '2️⃣',
            3: '3️⃣',
            4: '4️⃣',
            5: '5️⃣',
            6: '6️⃣',
            7: '7️⃣',
            8: '8️⃣',
            9: '9️⃣',
            10: '🔟',
        }

        for user in lst:
            val = ''
            for ans in self.user_answers[user.id]:
                val += emoji_map[ans]
            embed.add_field(
                name=f'{user.name}  ({self.score[user.id]})',
                value=val,
                inline=False
            )

    async def display_score(self):
        self.clear_items()
        embed = discord.Embed(
            title='Current score',
            color=0x0000ff
        )
        self.embed_score(embed, sort=False)

        if self.scoreboard:
            await self.scoreboard.edit(embed=embed)
        else:
            self.scoreboard = await self.channel.send(embed=embed)

    async def on_timeout(self):
        try:
            await self.itc.delete_original_response()
        except discord.NotFound:
            pass
