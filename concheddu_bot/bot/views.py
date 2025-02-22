import discord

from .. import models as m
from .cmd.music import get_vc_from_interaction, sense_check


def elide(text: str, length: int = 60) -> str:
    if len(text) > length:
        return text[:length - 3] + '...'
    return text

def pad(text: str, length: int = 60) -> str:
    return text.rjust(length, '.')

def elide_and_pad(text: str, length: int = 60) -> str:
    return elide(pad(text, length), length)

class SongItemFavorite(discord.ui.Button):
    def __init__(self, song: m.YTSong, favorite: bool, *args, **kwargs):
        self.fav = favorite
        label = self.get_label(favorite)
        style = self.get_style(favorite)
        super().__init__(label=label, style=style, *args, **kwargs)
        self.song = song

    async def callback(self, itc: discord.Interaction):
        fav = await self.song.favorite_toggle(server=itc.guild, user=itc.user)
        self.label = self.get_label(fav)
        self.style = self.get_style(fav)
        await self.view.itc.edit_original_response(view=self.view)
        await itc.response.defer()

    @staticmethod
    def get_style(favorite: bool) -> discord.ButtonStyle:
        return discord.ButtonStyle.success if favorite else discord.ButtonStyle.gray

    @staticmethod
    def get_label(favorite: bool) -> str:
        return '♥' if favorite else '♡'

class SongItemPlay(discord.ui.Button):
    def __init__(self, song: m.YTSong, *args, **kwargs):
        super().__init__(label='▶', style=discord.ButtonStyle.primary, *args, **kwargs)
        self.song = song

    @sense_check
    async def callback(self, itc: discord.Interaction):
        vc = await get_vc_from_interaction(itc)
        await self.song.play(vc, user=itc.user, server=itc.guild)
        # await self.view.itc.edit_original_response(view=self.view)
        await itc.response.defer()

    @staticmethod
    def elide_or_pad(text: str, length: int = 40) -> str:
        if len(text) > length:
            return text[:length - 3] + '...'
        return text.rjust(length, '_')

# Rewrite above to have a text with the title + 1 button  to favorite and one to play
class SongItemText(discord.ui.Button):
    def __init__(self, song: m.YTSong, row: int, *args, **kwargs):
        title = elide(song.title)
        super().__init__(
            label=title,
            style=discord.ButtonStyle.secondary,
            row=row,
            disabled=True,
            *args, **kwargs
        )

class SongItemDownload(discord.ui.Button):
    def __init__(self, song: m.YTSong, *args, **kwargs):
        super().__init__(label='⬇', style=discord.ButtonStyle.secondary, *args, **kwargs)
        self.song = song

    async def callback(self, itc: discord.Interaction):
        file_path = self.song.local_path
        if file_path is None:
            await itc.response.send_message(
                'Something went wrong',
                ephemeral=True,
                delete_after=5
            )
            return
        file = discord.File(file_path)
        await itc.response.send_message(
            'Downloading song (link last 60s)', file=file,
            ephemeral=True,
            delete_after=60
        )

class SongListView(discord.ui.View):
    def __init__(self, itc: discord.Interaction):
        super().__init__()
        self.itc = itc
        self.cnt = 0

        self.songs = []
        self.favs = []

    def add_song(self, song: m.YTSong, favorite: bool = False):
        self.songs.append(song)
        self.favs.append(favorite)
        if self.cnt >= 5:
            return
        row = self.cnt
        print(row)
        self.add_item(SongItemText(song, row=row))
        self.add_item(SongItemFavorite(song, favorite, row=row))
        self.add_item(SongItemDownload(song, row=row))
        self.add_item(SongItemPlay(song, row=row))
        self.cnt += 1

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

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

class SongListSelect(discord.ui.Select):
    def __init__(self, songs: list[m.YTSong], *args, **kwargs):
        options = [SongOption(song) for song in songs]
        super().__init__(placeholder='Select a song to play', options=options, *args, **kwargs)

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
        await itc.response.send_message(
            f'Playing [{song.duration} s] {song.title}',
            ephemeral=True,
            delete_after=5
        )

class SongListViewSelect(discord.ui.View):
    def __init__(self, itc: discord.Interaction, songs: list[m.YTSong]):
        super().__init__()
        self.itc = itc

        self.songs = songs

        if songs:
            self.add_item(SongListSelect(songs))
        else:
            self.add_item(discord.ui.Button(
                label='No songs found',
                style=discord.ButtonStyle.secondary,
                disabled=True
            ))

    async def on_timeout(self):
        await self.itc.delete_original_response()
