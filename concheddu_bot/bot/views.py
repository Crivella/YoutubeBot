import logging
import os

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
        # await self.view.itc.edit_original_response(view=self.view)

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
        # selected = []
        for opt in self.options_[self.page * MAX_LIST_OPT:(self.page + 1) * MAX_LIST_OPT]:
            opt.default = opt.value in values
            # if opt.value in values:
            #     selected.append(self.songs_map[opt.value])
            #     opt.default = True
            # else:
            #     opt.default = False

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

class CreatePlaylistSubmit(discord.ui.Button):
    def __init__(self, list, name, *args, **kwargs):
        super().__init__(
            label='Submit',
            style=discord.ButtonStyle.primary,
            *args, **kwargs
        )
        self.list = list
        self.name = name

    async def callback(self, itc: discord.Interaction):
        playlist = await m.Playlist.create_playlist(self.name, server=itc.guild, user=itc.user)
        logger.info(f'Creating playlist `{self.name}`:')
        for opt in self.list.options_:
            if opt.default:
                logger.info(f'  - {opt.song.title}')
                # print(f'Adding {opt.song.title} to playlist')
                await playlist.add_song(opt.song)
        await itc.response.send_message(
            f'Playlist `{self.name}` created',
            ephemeral=True
        )

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
        self.submit = CreatePlaylistSubmit(self.list, name, row=3,)

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

class QuizStarter(discord.ui.View):
    def __init__(self, itc: discord.Interaction, playlists: list[m.Playlist]):
        super().__init__()
        self.itc = itc
        # self.quiz = quiz

        users = self.itc.user.voice.channel.members

        self.select_users = UserList(users, min_values=1, max_values=len(users))
        self.select_playlists = PlaylistList(playlists, min_values=0, max_values=1)
        self.start = CallbackButton(
            label='Start Quiz',
            style=discord.ButtonStyle.primary
        )

        self.start.add_callback(self.start_quiz)

        self.add_item(self.select_playlists)
        self.add_item(self.select_users)
        self.add_item(self.start)

    @ensure_response(before=False, defer=True)
    async def start_quiz(self, itc: discord.Interaction, num_songs: int = 20):
        """Start a quiz: select atleast one user and a playlist to choose songs from.
        if no playlist is selected, the songs will be picked from all the songs in the server.

        Args:
            itc (discord.Interaction): Interaction
            num_songs (int, optional): The number of songs to pick from the playlist. Defaults to 20.
        """
        users = self.select_users.get_users()
        playlist = self.select_playlists.values
        if playlist:
            playlist = playlist[0]
        playlist = await m.Playlist.objects.aget(playlist) if playlist else None


        if not users:
            await safe_response(itc, 'Select at least one user', ephemeral=True, delete_after=10)
            return

        if playlist is None:
            songs = await m.YTSong.get_all_songs(server=itc.guild, n=num_songs, sorting='random')
        else:
            songs = await playlist.get_songs_order_random(n=num_songs)
        # playlist_id = self.playlist.values[0] if self.playlist.values else None

        logger.info(f'Command `start_quiz` called by `{itc.user.name}` [{itc.guild.name}]')
        for user in users:
            logger.info(f'Quiz user: {user}')
        for song in songs:
            logger.info(f'Quiz song: {song.title}')

    async def on_timeout(self):
        await self.itc.delete_original_response()
