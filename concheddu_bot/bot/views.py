import os

import discord

from .. import models as m
from .cmd.music import get_vc_from_interaction, sense_check

try:
    MAX_LIST_OPT = int(os.getenv('BOT_MAX_LIST_OPT', 10))
except ValueError:
    MAX_LIST_OPT = 10
if MAX_LIST_OPT > 25:
    MAX_LIST_OPT = 25

async def safe_defer(itc: discord.Interaction):
    try:
        await itc.response.defer()
    except discord.errors.NotFound:
        pass

def elide(text: str, length: int = 60) -> str:
    if len(text) > length:
        return text[:length - 3] + '...'
    return text

def pad(text: str, length: int = 60) -> str:
    return text.rjust(length, '.')

def elide_and_pad(text: str, length: int = 60) -> str:
    return elide(pad(text, length), length)

# class SongItemFavorite(discord.ui.Button):
#     def __init__(self, song: m.YTSong, favorite: bool, *args, **kwargs):
#         self.fav = favorite
#         label = self.get_label(favorite)
#         style = self.get_style(favorite)
#         super().__init__(label=label, style=style, *args, **kwargs)
#         self.song = song

#     async def callback(self, itc: discord.Interaction):
#         fav = await self.song.favorite_toggle(server=itc.guild, user=itc.user)
#         self.label = self.get_label(fav)
#         self.style = self.get_style(fav)
#         await self.view.itc.edit_original_response(view=self.view)
#         await itc.response.defer()

#     @staticmethod
#     def get_style(favorite: bool) -> discord.ButtonStyle:
#         return discord.ButtonStyle.success if favorite else discord.ButtonStyle.gray

#     @staticmethod
#     def get_label(favorite: bool) -> str:
#         return '♥' if favorite else '♡'

# class SongItemPlay(discord.ui.Button):
#     def __init__(self, song: m.YTSong, *args, **kwargs):
#         super().__init__(label='▶', style=discord.ButtonStyle.primary, *args, **kwargs)
#         self.song = song

#     @sense_check
#     async def callback(self, itc: discord.Interaction):
#         vc = await get_vc_from_interaction(itc)
#         await self.song.play(vc, user=itc.user, server=itc.guild)
#         # await self.view.itc.edit_original_response(view=self.view)
#         await itc.response.defer()

#     @staticmethod
#     def elide_or_pad(text: str, length: int = 40) -> str:
#         if len(text) > length:
#             return text[:length - 3] + '...'
#         return text.rjust(length, '_')

# # Rewrite above to have a text with the title + 1 button  to favorite and one to play
# class SongItemText(discord.ui.Button):
#     def __init__(self, song: m.YTSong, row: int, *args, **kwargs):
#         title = elide(song.title)
#         super().__init__(
#             label=title,
#             style=discord.ButtonStyle.secondary,
#             row=row,
#             disabled=True,
#             *args, **kwargs
#         )

# class SongItemDownload(discord.ui.Button):
#     def __init__(self, song: m.YTSong, *args, **kwargs):
#         super().__init__(label='⬇', style=discord.ButtonStyle.secondary, *args, **kwargs)
#         self.song = song

#     async def callback(self, itc: discord.Interaction):
#         file_path = self.song.local_path
#         if file_path is None:
#             await itc.response.send_message(
#                 'Something went wrong',
#                 ephemeral=True,
#                 delete_after=5
#             )
#             return
#         file = discord.File(file_path)
#         await itc.response.send_message(
#             'Downloading song (link last 60s)', file=file,
#             ephemeral=True,
#             delete_after=60
#         )

# class SongListView(discord.ui.View):
#     def __init__(self, itc: discord.Interaction):
#         super().__init__()
#         self.itc = itc
#         self.cnt = 0

#         self.songs = []
#         self.favs = []

#     def add_song(self, song: m.YTSong, favorite: bool = False):
#         self.songs.append(song)
#         self.favs.append(favorite)
#         if self.cnt >= 5:
#             return
#         row = self.cnt
#         print(row)
#         self.add_item(SongItemText(song, row=row))
#         self.add_item(SongItemFavorite(song, favorite, row=row))
#         self.add_item(SongItemDownload(song, row=row))
#         self.add_item(SongItemPlay(song, row=row))
#         self.cnt += 1

#     async def on_timeout(self):
#         for item in self.children:
#             item.disabled = True

class SongOption(discord.SelectOption):
    def __init__(self, song: m.YTSong, *args, **kwargs):
        super().__init__(
            label=elide(song.title),
            value=song.youtube_id,
            description=f'[{song.duration} s]',
            emoji='🎵',
            *args, **kwargs
        )
        self.song = song

class ButtonFwd(discord.ui.Button):
    def __init__(self, list, *args, **kwargs):
        self.list = list
        if self.list.num_pages == 0:
            kwargs['disabled'] = True
        super().__init__(
            label='>',
            style=discord.ButtonStyle.primary,
            *args, **kwargs
        )

    async def callback(self, itc: discord.Interaction):
        self.list.page_forward()
        await self.view.itc.edit_original_response(view=self.view)
        await safe_defer(itc)

class ButtonBwd(discord.ui.Button):
    def __init__(self, list, *args, **kwargs):
        self.list = list
        if self.list.num_pages == 0:
            kwargs['disabled'] = True
        super().__init__(
            label='<',
            style=discord.ButtonStyle.primary,
            *args, **kwargs
        )

    async def callback(self, itc: discord.Interaction):
        self.list.page_backward()
        await self.view.itc.edit_original_response(view=self.view)
        await safe_defer(itc)

class ListPlay(discord.ui.Select):
    def __init__(self, songs: list[m.YTSong], *args, **kwargs):

        self.options_ = options = [SongOption(song) for song in songs]
        self.page = 0
        self.num_pages = len(options) // MAX_LIST_OPT
        super().__init__(
            placeholder='Select a song to play',
            options=options[:MAX_LIST_OPT],
            *args, **kwargs
        )

    def page_forward(self):
        self.go_to_page(self.page + 1)

    def page_backward(self):
        self.go_to_page(self.page - 1)

    def go_to_page(self, page: int):
        if page < 0 or page > self.num_pages:
            return
        self.page = page
        start = page * MAX_LIST_OPT
        end = start + MAX_LIST_OPT

        lst = self.options_[start:end]
        self.options = lst

    @sense_check
    async def callback(self, itc: discord.Interaction):
        song_id = self.values[0]
        for opt in self.options:
            if opt.value == song_id:
                song = opt.song
                break
        else:
            raise ValueError('Song not found')

        vc = await get_vc_from_interaction(itc)
        await song.play(vc, user=itc.user, server=itc.guild)
        try:
            await itc.response.send_message(
                f'Playing [{song.duration} s] {song.title}',
                ephemeral=True,
                delete_after=5
            )
        except discord.errors.NotFound:
            pass

class ListMultiSelect(discord.ui.Select):
    def __init__(self, songs: list[m.YTSong], *args, **kwargs):

        self.options_ = options = [SongOption(song) for song in songs]
        self.page = 0
        self.num_pages = len(options) // MAX_LIST_OPT
        super().__init__(
            placeholder='Select a song to play',
            options=options[:MAX_LIST_OPT],
            *args, **kwargs
        )

    def page_forward(self):
        self.go_to_page(self.page + 1)

    def page_backward(self):
        self.go_to_page(self.page - 1)

    def go_to_page(self, page: int):
        if page < 0 or page > self.num_pages:
            return
        self.page = page
        start = page * self.MAX_OPTS
        end = start + self.MAX_OPTS

        lst = self.options_[start:end]
        self.options = lst

    @sense_check
    async def callback(self, itc: discord.Interaction):
        for song_id in self.values:
            for opt in self.options:
                if opt.value == song_id:
                    opt.default = not opt.default
                    break
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

        self.list = ListPlay(songs, row=0)
        self.add_item(self.list, )

        self.jb1 = ButtonBwd(self.list, row=1)
        self.jf1 = ButtonFwd(self.list, row=1)
        self.add_item(self.jb1)
        self.add_item(self.jf1)

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
        # print(name)
        # for opt in self.list.options_:
        #     if opt.default:
        #         print(opt.song)
        # await safe_defer(itc)
        # return
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
        self.list = ListMultiSelect(songs, row=1, min_values=0, max_values=mv)
        self.jb1 = ButtonBwd(self.list, row=2)
        self.jf1 = ButtonFwd(self.list, row=2)
        self.submit = CreatePlaylistSubmit(self.list, name, row=3)

        self.add_item(self.list)
        self.add_item(self.jb1)
        self.add_item(self.jf1)
        self.add_item(self.submit)

    async def on_timeout(self):
        await self.itc.delete_original_response()
