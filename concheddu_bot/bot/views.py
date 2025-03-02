import os

import discord

from .. import models as m
from .utils import get_vc_from_interaction, safe_defer, sense_check

try:
    MAX_LIST_OPT = int(os.getenv('BOT_MAX_LIST_OPT', 10))
except ValueError:
    MAX_LIST_OPT = 10
if MAX_LIST_OPT > 25:
    MAX_LIST_OPT = 25


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

class ButtonFwd(discord.ui.Button):
    def __init__(self, list, page_btn, *args, **kwargs):
        self.list = list
        if self.list.num_pages == 0:
            kwargs['disabled'] = True
        super().__init__(
            label='>',
            style=discord.ButtonStyle.primary,
            *args, **kwargs
        )
        self.bwd_btn = None
        self.page_btn = page_btn

    async def callback(self, itc: discord.Interaction):
        if self.list.page_forward():
            self.page_btn.label = str(self.list.page+1)
            self.disabled = self.list.page >= self.list.num_pages
            self.bwd_btn.disabled = False
            await self.view.itc.edit_original_response(view=self.view)

        await safe_defer(itc)

class ButtonPageNum(discord.ui.Button):
    def __init__(self, *args, **kwargs):
        self.list = list
        super().__init__(
            label='1',
            disabled=True,
            style=discord.ButtonStyle.secondary,
            *args, **kwargs
        )

class ButtonBwd(discord.ui.Button):
    def __init__(self, list, page_btn, *args, **kwargs):
        self.list = list
        super().__init__(
            label='<',
            disabled=True,
            style=discord.ButtonStyle.primary,
            *args, **kwargs
        )
        self.fwd_btn = None
        self.page_btn = page_btn

    async def callback(self, itc: discord.Interaction):
        if self.list.page_backward():
            self.page_btn.label = str(self.list.page+1)
            self.disabled = self.list.page <= 0
            self.fwd_btn.disabled = False
            await self.view.itc.edit_original_response(view=self.view)
        await safe_defer(itc)

class Paged:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.page = 0
        self.options__ = []
        self.num_pages = 0
        self.follow_changes = False

    @property
    def options_(self):
        return self.options__
    @options_.setter
    def options_(self, value):
        self.options__ = value
        self.num_pages = len(value) // MAX_LIST_OPT

    def page_forward(self):
        return self.go_to_page(self.page + 1)

    def page_backward(self):
        return self.go_to_page(self.page - 1)

    def go_to_page(self, page: int):
        if page < 0 or page > self.num_pages:
            return False
        self.page = page
        start = page * MAX_LIST_OPT
        end = start + MAX_LIST_OPT

        lst = self.options_[start:end]
        if self.follow_changes:
            self.max_values = min(MAX_LIST_OPT, len(lst))
        self.options = lst
        return True

class ListPlay(discord.ui.Select, Paged):
    def __init__(self, songs: list[m.YTSong], *args, **kwargs):
        super().__init__(
            placeholder='Select a song to play',
            min_values=0,
            max_values=1,
            options=[],
            *args, **kwargs
        )
        self.follow_changes = False
        self.songs = songs

        self.options_ = [SongOption(song) for song in songs]
        self.songs_map = {opt.value: opt.song for opt in self.options_}
        self.go_to_page(0)

    @sense_check
    async def callback(self, itc: discord.Interaction):
        if not self.values:
            await safe_defer(itc)
            return
        song_id = self.values[0]
        song = self.songs_map.get(song_id)

        try:
            await itc.response.send_message(
                f'Playing [{song.duration} s] {song.title}',
                ephemeral=True,
                delete_after=15
            )
        except discord.errors.NotFound:
            pass
        await song.play(user=itc.user, server=itc.guild)

class ListMultiSelect(discord.ui.Select, Paged):
    def __init__(self, songs: list[m.YTSong], *args, **kwargs):
        super().__init__(
            placeholder='Select a song to play',
            options=[],
            *args, **kwargs
        )
        self.follow_changes = True
        self.songs = songs
        self.options_ = [SongOption(song) for song in songs]
        self.go_to_page(0)

    async def callback(self, itc: discord.Interaction):
        values = set(self.values)
        for opt in self.options:
            opt.default = opt.value in values

        await safe_defer(itc)

class SongList(discord.ui.View):
    def __init__(self, itc: discord.Interaction, songs: list[m.YTSong]):
        super().__init__()
        self.itc = itc

        self.songs = songs

        if not songs:
            self.add_item(discord.ui.Button(
                label='No songs found',
                style=discord.ButtonStyle.secondary,
                disabled=True
            ))
            return

        page_btn = ButtonPageNum()
        self.list = ListPlay(songs, row=0)
        self.add_item(self.list, )

        self.jb1 = ButtonBwd(self.list, page_btn, row=1)
        self.jf1 = ButtonFwd(self.list, page_btn, row=1)
        self.jb1.fwd_btn = self.jf1
        self.jf1.bwd_btn = self.jb1
        self.add_item(self.jb1)
        self.add_item(page_btn)
        self.add_item(self.jf1)

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

        for opt in self.list.options_:
            if opt.default:
                await playlist.add_song(opt.song)
        await itc.response.send_message(
            f'Playlist `{self.name}` created',
            ephemeral=True
        )

class CreatePlaylist(discord.ui.View):
    def __init__(self, itc: discord.Interaction, songs: list[m.YTSong], name):
        super().__init__()
        self.itc = itc

        self.songs = songs
        self.name_ = name

        if not songs:
            self.add_item(discord.ui.Button(
                label='No songs found',
                style=discord.ButtonStyle.secondary,
                disabled=True
            ))
            return

        mv = min(MAX_LIST_OPT, len(songs))
        btn = ButtonPageNum(row=2)
        self.list = ListMultiSelect(songs, row=1, min_values=0, max_values=mv)
        self.jb1 = ButtonBwd(self.list, btn, row=2)
        self.jf1 = ButtonFwd(self.list, btn, row=2)
        self.jb1.fwd_btn = self.jf1
        self.jf1.bwd_btn = self.jb1
        self.submit = CreatePlaylistSubmit(self.list, name, row=3)

        self.add_item(self.list)
        self.add_item(self.jb1)
        self.add_item(btn)
        self.add_item(self.jf1)
        self.add_item(self.submit)

    async def on_timeout(self):
        await self.itc.delete_original_response()
