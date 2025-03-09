import random
from collections import defaultdict

import discord

from ... import models as m
from ..utils import ensure_response, ensure_user, safe_response
from .buttons import CallbackButton
from .utils import elide, logger


class UserList(discord.ui.Select):
    def __init__(self, users: list[discord.Member], *args, **kwargs):
        super().__init__(
            placeholder='Select a user',
            options=[
                discord.SelectOption(
                    label=elide(user.name),
                    value=user.id,
                    emoji='👤'
                ) for user in users
            ],
            *args, **kwargs
        )
        self.map = {str(user.id): user for user in users}

    @ensure_response(before=False, defer=True)
    async def callback(self, itc: discord.Interaction):
        pass

    def get_users(self):
        return [self.map[user_id] for user_id in self.values]


class PlaylistList(discord.ui.Select):
    def __init__(self, playlists: list[m.Playlist], *args, **kwargs):
        if not playlists:
            super().__init__(
                placeholder='No playlists found',
                options=[
                    discord.SelectOption(
                        label='No playlists found',
                        value='__NO__NE__',
                    )
                ],
                *args, **kwargs
            )
        else:
            super().__init__(
                placeholder='Select a playlist',
                options=[
                    discord.SelectOption(
                        label=elide(playlist.name),
                        value=playlist.id,
                        description=f'{playlist.song_count} songs, {playlist.duration} s',
                        emoji='📁'
                    ) for playlist in playlists
                ],
                *args, **kwargs
            )

    @ensure_response(before=False, defer=True)
    async def callback(self, itc: discord.Interaction):
        pass

class ListAnswer(discord.ui.Select):
    def __init__(self, songs: list[m.YTSong], user: discord.Member, *args, **kwargs):
        super().__init__(
            placeholder='Select an answer',
            options=[
                discord.SelectOption(
                    label=elide(song.title),
                    value=song.youtube_id,
                    # description=f'[{song.duration} s] [{song.times_played_} plays]',
                    emoji='🎵'
                ) for song in songs
            ],
            *args, **kwargs
        )
        self.user = user
        self.songs_map = {song.youtube_id: song for song in songs}
        # self.selected = None

    @ensure_response(before=False, defer=True)
    async def callback(self, itc: discord.Interaction):
        pass

    # @ensure_response(defer=True)
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user.id


class QuizSongs(discord.ui.View):
    def __init__(
            self,
            itc: discord.Interaction,
            playlists: list[m.Playlist],
            num_songs: int = 5,
            num_choices: int = 5,
            segment_length: int = 20,
            segment_mode: str = 'start'
        ):
        super().__init__()
        self.itc = itc
        self.channel = itc.channel
        self.num_songs = num_songs
        self.nmc = num_choices
        self.segment_length = segment_length
        self.segment_mode = segment_mode
        # self.quiz = quiz

        users = self.itc.user.voice.channel.members

        self.select_users = UserList(users, min_values=1, max_values=len(users))
        self.select_playlists = PlaylistList(playlists, min_values=0, max_values=1)
        self.start = CallbackButton(
            label='Start Quiz',
            style=discord.ButtonStyle.primary
        )

        self.start.add_callback(self.submit_quiz)

        self.add_item(self.select_playlists)
        self.add_item(self.select_users)
        self.add_item(self.start)

        self.idx = 0
        self.users: list[discord.Member] = []
        self.user_map: dict[int, discord.Member] = {}
        self.user_colors: dict[int, discord.Color] = defaultdict(discord.Color.random)
        self.songs: list[m.YTSong] = []
        self.score: dict[int, int] = {}
        self.answers: list[bool] = []
        self.user_answers: dict[int, list[bool]] = defaultdict(list)

        self.scoreboard: discord.Message = None

    async def quiz_step(self):
        if self.idx >= len(self.songs):
            await self.quiz_finish()
            return

        user = self.users[self.idx % len(self.users)]
        song = self.songs[self.idx]

        view = discord.ui.View()

        server = await m.DiscordServer.from_discord_guild(self.itc.guild)
        message = None
        answered = False

        # Instead of using the current list of song pick X random songs + the current song
        choices = random.sample(self.all_song, self.nmc)
        if song not in choices:
            choices[-1] = song
        random.shuffle(choices)
        self.answer_list = ListAnswer(choices, user)

        self.play_stop = CallbackButton(
            label='STOP',
            style=discord.ButtonStyle.danger
        )
        self.play_start = CallbackButton(
            label='PLAY',
            style=discord.ButtonStyle.success
        )
        self.answer_btn = CallbackButton(
            label='SUBMIT',
            style=discord.ButtonStyle.primary
        )

        enqueueing = False

        if self.segment_mode == 'start':
            start = 0
            end = self.segment_length
        elif self.segment_mode == 'end':
            start = song.duration - self.segment_length
            end = song.duration
        elif self.segment_mode == 'random':
            start = random.randint(0, song.duration - self.segment_length)
            end = start + self.segment_length

        @ensure_response(before=False, defer=True)
        @ensure_user(users=[user], defer=True)
        async def play_callback(itc: discord.Interaction):
            nonlocal enqueueing
            if answered:
                return
            if enqueueing:
                return
            enqueueing = True
            await song.play(
                update_msg=False, itc=itc,
                start=start, end=end
            )
            enqueueing = False

        @ensure_response(before=False, defer=True)
        @ensure_user(users=[user], defer=True)
        async def stop_callback(itc: discord.Interaction):
            nonlocal enqueueing
            if answered:
                return
            enqueueing = False
            await server.clear()

        @ensure_response(before=False, defer=True)
        @ensure_user(users=[user], defer=True)
        async def answer_callback(itc: discord.Interaction):
            nonlocal message, answered, enqueueing
            if answered:
                return
            values = self.answer_list.values
            if not values:
                await safe_response(itc, 'Select an answer', ephemeral=True, delete_after=10)
                return

            answered = True
            enqueueing = False
            answer = values[0]
            await server.clear()

            user_obj = await m.DiscordUser.from_discord_user(user)
            result = await song.guess_ytid(answer, user=user_obj)

            msg = []
            title = f'{user.nick}: ' + 'Correct ❤️❤️' if result else 'Incorrect 🙁🙁'
            msg.append(f'Real answer: {song.title}')
            msg.append(f'Your answer: {self.answer_list.songs_map[answer].title}')
            embed = discord.Embed(
                title=title,
                description='\n'.join(msg),
                color=self.user_colors[user.id]
            )

            self.answers.append(result)
            self.user_answers[user.id].append(result)
            self.score[user.id] += result

            view.clear_items()
            await message.edit(embed=embed, view=None)
            await self.display_score()
            self.idx += 1
            await self.quiz_step()

        self.play_start.add_callback(play_callback)
        self.play_stop.add_callback(stop_callback)
        self.answer_btn.add_callback(answer_callback)

        view.add_item(self.answer_list)
        view.add_item(self.play_stop)
        view.add_item(self.play_start)
        view.add_item(self.answer_btn)
        msg = f'<@{user.id}> \'s turn'
        message = await self.channel.send(content=msg, view=view)

    async def quiz_finish(self):
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
        self.embed_score(embed, sort=True)
        await self.channel.send(embed=embed)
        await safe_response(self.itc, 'Quiz finished!!!')
        # await self.itc.delete_original_response()

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

        playlist = self.select_playlists.values
        if playlist:
            playlist = playlist[0]
        if playlist is None or playlist == '__NO__NE__':
            playlist = None
        else:
            playlist = await m.Playlist.objects.aget(id=playlist) if playlist else None

        if not users:
            await safe_response(itc, 'Select at least one user', ephemeral=True, delete_after=10)
            return

        if playlist is None:
            songs = await m.YTSong.get_all_songs(server=itc.guild, sorting='random')
        else:
            songs = await playlist.get_all_songs(sorting='random')
        # playlist_id = self.playlist.values[0] if self.playlist.values else None

        needed_songs = len(users) * self.num_songs
        found_songs = len(songs)
        if found_songs < needed_songs:
            await safe_response(
                itc, f'Not enough songs found in global/playlist ({found_songs}/{needed_songs})',
                ephemeral=True, delete_after=10
            )
            return
        logger.info(f'Found {found_songs} songs')

        self.all_song = songs
        songs = songs[:needed_songs]

        self.users = users
        self.user_map = {user.id: user for user in users}
        self.score = {user.id: 0 for user in users}
        self.songs = songs
        logger.info('Quiz users:')
        for user in users:
            logger.info(f'  - {user.name}')
        logger.info('Quiz songs:')
        for song in songs:
            logger.info(f' - {song.title}')

        self.clear_items()
        msg = []
        msg.append(f'Quiz started with {len(users)} users and {len(songs)} songs')
        msg.append(f'- Each user will have to guess {self.num_songs} songs')
        msg.append(f'- Each song will have {self.nmc} choices')
        msg.append(f'- Segment length: {self.segment_length} s')
        msg.append(f'- Segment mode: {self.segment_mode}')
        await safe_response(self.itc, '\n'.join(msg), ephemeral=True, view=None)
        await self.display_score()
        await self.quiz_step()

    def embed_score(self, embed: discord.Embed, sort: bool = True):
        if sort:
            lst = sorted(self.users, key=lambda user: self.score[user.id])[::-1]
        else:
            lst = self.users

        for user in lst:
            val = ''
            for ans in self.user_answers[user.id]:
                val += '✅' if ans else '❌'
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
        await self.itc.delete_original_response()
