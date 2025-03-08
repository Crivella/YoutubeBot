import logging
import os
import random
from collections import defaultdict

import discord

from .. import models as m
from .utils import ensure_response, safe_response, sense_check

try:
    MAX_LIST_OPT = int(os.getenv('BOT_MAX_LIST_OPT', 10))
except ValueError:
    MAX_LIST_OPT = 10
if MAX_LIST_OPT > 25:
    MAX_LIST_OPT = 25

logger = logging.getLogger('bot')

def elide(text: str, length: int = 60) -> str:
    if len(text) > length:
        return text[:length - 3] + '...'
    return text

def pad(text: str, length: int = 60) -> str:
    return text.rjust(length, '.')

def elide_and_pad(text: str, length: int = 60) -> str:
    return elide(pad(text, length), length)

class SongOption(discord.SelectOption):
    def __init__(self, song: m.YTSong, *args,**kwargs):
        super().__init__(
            label=elide(song.title),
            value=song.youtube_id,
            description=f'[{song.duration} s] [{song.times_played_} plays]',
            emoji='🎵',
            *args, **kwargs
        )
        self.song = song

class CallbackButton(discord.ui.Button):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.callbacks = []

    def add_callback(self, callback):
        self.callbacks.append(callback)

    @ensure_response(before=True, defer=True)
    async def callback(self, itc: discord.Interaction):
        for callback in self.callbacks:
            await callback(itc)

class Paged:
    def __init__(
            self,
            bwd_btn: CallbackButton,
            pge_btn: CallbackButton,
            fwd_btn: CallbackButton,
            *args, **kwargs
        ):
        super().__init__(*args, **kwargs)

        self.bwd_btn = bwd_btn
        self.pge_btn = pge_btn
        self.fwd_btn = fwd_btn

        bwd_btn.add_callback(self.page_backward)
        fwd_btn.add_callback(self.page_forward)
        pge_btn.disabled = True

        self.page = None
        self.options__: list[SongOption] = []
        self.num_pages = 0
        self.follow_changes = False

    @property
    def options_(self):
        return self.options__
    @options_.setter
    def options_(self, value):
        self.options__ = value
        self.num_pages = (len(value) - 1) // MAX_LIST_OPT

    async def page_forward(self, *args):
        return await self.go_to_page(self.page + 1)

    async def page_backward(self, *args):
        return await self.go_to_page(self.page - 1)

    async def go_to_page(self, page: int) -> bool:
        logger.debug(f'go_to_page: {page} / {self.num_pages} , {self.page}')
        if page < 0 or page > self.num_pages:
            return False
        if page == self.page:
            return True
        self.page = page
        start = page * MAX_LIST_OPT
        end = start + MAX_LIST_OPT

        lst = self.options_[start:end]
        if self.follow_changes:
            self.max_values = min(MAX_LIST_OPT, len(lst))
        self.options = lst

        self.bwd_btn.disabled = page <= 0
        self.fwd_btn.disabled = page >= self.num_pages
        self.pge_btn.label = f'{page+1} / {self.num_pages+1}'
        await safe_response(self.view.itc, view=self.view)

class ListPlay(Paged, discord.ui.Select):
    def __init__(
            self,
            songs: list[m.YTSong],
            *args,
            **kwargs
        ):
        logger.debug(f'ListPlay: {len(songs)}')
        opts = [SongOption(song) for song in songs]
        super().__init__(
            placeholder='Select a song to play',
            min_values=0,
            max_values=1,
            options=opts[:MAX_LIST_OPT],
            *args, **kwargs
        )
        self.follow_changes = False

        self.options_ = opts
        self.songs_map = {opt.value: opt.song for opt in opts}

    @sense_check
    @ensure_response(before=False, defer=True)
    async def callback(self, itc: discord.Interaction):
        if not self.values:
            return
        song_id = self.values[0]
        song = self.songs_map.get(song_id)

        await song.play(itc=itc)

class ListMultiSelect(Paged, discord.ui.Select):
    def __init__(self, songs: list[m.YTSong], *args, **kwargs):
        logger.debug(f'ListMultiSelect: {len(songs)}')
        opts = [SongOption(song) for song in songs]
        super().__init__(
            placeholder='Select a song to play',
            options=opts[:MAX_LIST_OPT],
            *args, **kwargs
        )
        self.follow_changes = True
        self.options_ = opts
        self.songs_map = {opt.value: opt.song for opt in opts}

    @ensure_response(before=False, defer=True)
    async def callback(self, itc: discord.Interaction):
        values = set(self.values)
        for opt in self.options_[self.page * MAX_LIST_OPT:(self.page + 1) * MAX_LIST_OPT]:
            opt.default = opt.value in values

class SongList(discord.ui.View):
    def __init__(self, itc: discord.Interaction, songs: list[m.YTSong]):
        super().__init__()
        self.itc = itc

        # self.songs = songs

        if not songs:
            self.add_item(discord.ui.Button(
                label='No songs found',
                style=discord.ButtonStyle.secondary,
                disabled=True
            ))
            return

        bwd_btn = CallbackButton(label='<', row=1, style=discord.ButtonStyle.primary)
        pge_btn = CallbackButton(label='1', row=1, disabled=True, style=discord.ButtonStyle.secondary)
        fwd_btn = CallbackButton(label='>', row=1, style=discord.ButtonStyle.primary)
        self.list = ListPlay(songs, row=0, bwd_btn=bwd_btn, pge_btn=pge_btn, fwd_btn=fwd_btn)
        self.add_item(self.list, )

        self.add_item(bwd_btn)
        self.add_item(pge_btn)
        self.add_item(fwd_btn)

    async def on_timeout(self):
        await self.itc.delete_original_response()

class CreatePlaylist(discord.ui.View):
    def __init__(self, itc: discord.Interaction, songs: list[m.YTSong], name):
        super().__init__()
        self.itc = itc

        # self.songs = songs
        self.name_ = name

        if not songs:
            self.add_item(discord.ui.Button(
                label='No songs found',
                style=discord.ButtonStyle.secondary,
                disabled=True
            ))
            return

        mv = min(MAX_LIST_OPT, len(songs))
        # btn = ButtonPageNum(row=2)
        bwd_btn = CallbackButton(label='<', row=2, style=discord.ButtonStyle.primary)
        pge_btn = CallbackButton(label='1', row=2, disabled=True, style=discord.ButtonStyle.secondary)
        fwd_btn = CallbackButton(label='>', row=2, style=discord.ButtonStyle.primary)
        self.list = ListMultiSelect(
            songs, row=1, min_values=0, max_values=mv,
            bwd_btn=bwd_btn, pge_btn=pge_btn, fwd_btn=fwd_btn
            )

        async def submit_callback(itc: discord.Interaction):
            playlist = await m.Playlist.create_playlist(self.name_, server=itc.guild, user=itc.user)
            logger.info(f'Creating playlist `{self.name_}`:')
            for opt in self.list.options_:
                if opt.default:
                    logger.info(f'  - {opt.song.title}')
                    # print(f'Adding {opt.song.title} to playlist')
                    await playlist.add_song(opt.song)
            await itc.response.send_message(
                f'Playlist `{self.name_}` created',
                ephemeral=True
            )

        self.submit = CallbackButton(
            label='Submit',
            style=discord.ButtonStyle.primary,
            row=3
        )
        self.submit.add_callback(submit_callback)

        self.add_item(self.list)
        self.add_item(bwd_btn)
        self.add_item(pge_btn)
        self.add_item(fwd_btn)
        self.add_item(self.submit)

    async def on_timeout(self):
        await self.itc.delete_original_response()

class ListMultiSelect2(Paged, discord.ui.Select):
    def __init__(self, songs: list[m.YTSong], defaults: list[m.YTSong], *args, **kwargs):
        logger.debug(f'ListMultiSelect2: {len(songs)}')
        opts = [SongOption(song) for song in songs]
        for opt in opts:
            opt.default = opt.song in defaults
        super().__init__(
            placeholder='Select a song to play',
            options=opts[:MAX_LIST_OPT],
            *args, **kwargs
        )
        self.follow_changes = True
        self.options_ = opts
        self.songs_map = {opt.value: opt.song for opt in opts}

    @ensure_response(before=False, defer=True)
    async def callback(self, itc: discord.Interaction):
        values = set(self.values)
        for opt in self.options_[self.page * MAX_LIST_OPT:(self.page + 1) * MAX_LIST_OPT]:
            opt.default = opt.value in values

class EditPlaylist(discord.ui.View):
    def __init__(
            self,
            itc: discord.Interaction,
            playlist: m.Playlist, songs: list[m.YTSong], defaults: list[m.YTSong],
            new_name: str = None
        ):
        super().__init__()
        self.itc = itc
        self.playlist = playlist

        if not songs:
            self.add_item(discord.ui.Button(
                label='No songs found',
                style=discord.ButtonStyle.secondary,
                disabled=True
            ))
            return

        mv = min(MAX_LIST_OPT, len(songs))
        bwd_btn = CallbackButton(label='<', row=2, style=discord.ButtonStyle.primary)
        pge_btn = CallbackButton(label='1', row=2, disabled=True, style=discord.ButtonStyle.secondary)
        fwd_btn = CallbackButton(label='>', row=2, style=discord.ButtonStyle.primary)
        self.list = ListMultiSelect2(
            songs,
            defaults,
            row=1, min_values=0, max_values=mv,
            bwd_btn=bwd_btn, pge_btn=pge_btn, fwd_btn=fwd_btn
        )

        async def submit_callback(itc: discord.Interaction):
            logger.info(f'Editing playlist `{playlist.name}`:')
            for opt in self.list.options_:
                if opt.default:
                    logger.info(f'  PRESENT - {opt.song.title}')
                    # print(f'Adding {opt.song.title} to playlist')
                    await playlist.add_song(opt.song)
                else:
                    logger.info(f'  ABSENT - {opt.song.title}')
                    # print(f'Removing {opt.song.title} from playlist')
                    await playlist.remove_song(opt.song)
            msg = [f'Playlist `{playlist.name}` edited']
            if new_name:
                await playlist.rename(new_name)
                msg.append(f'Playlist renamed to `{new_name}`')
            self.clear_items()
            await safe_response(itc, '\n'.join(msg), view=None)

        self.submit = CallbackButton(
            label='Submit',
            style=discord.ButtonStyle.primary,
            row=3
        )
        self.submit.add_callback(submit_callback)

        self.add_item(self.list)
        self.add_item(bwd_btn)
        self.add_item(pge_btn)
        self.add_item(fwd_btn)
        self.add_item(self.submit)

    async def on_timeout(self):
        await self.itc.delete_original_response()


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

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user.id


class QuizStarter(discord.ui.View):
    def __init__(
            self,
            itc: discord.Interaction,
            playlists: list[m.Playlist],
            num_songs: int = 20,
            num_choices: int = 5
        ):
        super().__init__()
        self.itc = itc
        self.channel = itc.channel
        self.num_songs = num_songs
        self.nmc = num_choices
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
        choices = [song]
        while song in choices:
            choices = await m.YTSong.get_all_songs(server=self.itc.guild, n=self.nmc-1, sorting='random')
        choices.append(song)
        random.shuffle(choices)
        self.answer_list = ListAnswer(choices, user)

        self.play_stop = CallbackButton(
            label='⏹️',
            style=discord.ButtonStyle.danger
        )
        self.play_start = CallbackButton(
            label='▶️',
            style=discord.ButtonStyle.success
        )
        self.answer_btn = CallbackButton(
            label='SUBMIT',
            style=discord.ButtonStyle.primary
        )

        enqueueing = False

        @ensure_response(before=False, defer=True)
        async def play_callback(itc: discord.Interaction):
            nonlocal enqueueing
            if answered:
                return
            if itc.user.id != user.id:
                await safe_response(
                    itc, 'You cannot play for someone else',
                    ephemeral=True, delete_after=10
                    )
            if enqueueing:
                return
            enqueueing = True
            await song.play(update_msg=False, itc=itc)
            enqueueing = False

        @ensure_response(before=False, defer=True)
        async def stop_callback(itc: discord.Interaction):
            nonlocal enqueueing
            if answered:
                return
            if itc.user.id != user.id:
                await safe_response(
                    itc, 'You cannot stop for someone else',
                    ephemeral=True, delete_after=10
                    )
            enqueueing = False
            await server.clear()

        @ensure_response(before=False, defer=True)
        async def answer_callback(itc: discord.Interaction):
            nonlocal message, answered, enqueueing
            if answered:
                return
            values = self.answer_list.values
            if itc.user.id != user.id:
                await safe_response(
                    itc, 'You cannot answer for someone else',
                    ephemeral=True, delete_after=10
                    )
            if not values:
                await safe_response(
                    itc, 'Select an answer',
                    ephemeral=True, delete_after=10
                    )
                return

            answered = True
            enqueueing = False
            answer = values[0]
            await server.clear()

            result = answer == song.youtube_id

            msg = []
            msg.append('Correct ❤️❤️' if result else 'Incorrect 🙁🙁')
            msg.append(f'Real answer: {song.title}')
            msg.append(f'Your answer: {self.answer_list.songs_map[answer].title}')
            embed = discord.Embed(
                title=user.name,
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

        # self.add_item(self.prev_song)
        view.add_item(self.answer_list)
        view.add_item(self.play_stop)
        view.add_item(self.play_start)
        view.add_item(self.answer_btn)
        # self.add_item(self.next_song)

        embed = discord.Embed(
            title=f'{user.name}\'s turn',
            color=self.user_colors[user.id]
        )
        message = await self.channel.send(embed=embed, view=view)
        # await safe_response(itc, view=self)

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
        await self.itc.delete_original_response()

    @ensure_response(before=False, defer=True)
    async def submit_quiz(self, itc: discord.Interaction):
        """Start a quiz: select atleast one user and a playlist to choose songs from.
        if no playlist is selected, the songs will be picked from all the songs in the server.

        Args:
            itc (discord.Interaction): Interaction
            num_songs (int, optional): The number of songs to pick from the playlist. Defaults to 20.
        """
        users = self.select_users.get_users()
        #random order for the users
        random.shuffle(users)
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
            songs = await m.YTSong.get_all_songs(server=itc.guild, n=self.num_songs, sorting='random')
        else:
            songs = await playlist.get_songs_order_random(limit=self.num_songs)
        # playlist_id = self.playlist.values[0] if self.playlist.values else None

        found_songs = len(songs)
        if found_songs < len(users):
            await safe_response(itc, 'Not enough songs found, need atleast 1 per user', ephemeral=True, delete_after=10)
            return
        found_songs -= found_songs % len(users)
        songs = songs[:found_songs]

        logger.info(f'Command `start_quiz` called by `{itc.user.name}` [{itc.guild.name}]')
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
                inline=True
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
