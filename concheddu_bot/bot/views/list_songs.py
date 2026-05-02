import discord

from ...youtube import YTDLSource
from ... import models as m
from .paged import ListPlay


class SongList(discord.ui.View):
    def __init__(self, itc: discord.Interaction, songs: list[m.YTSong]):
        super().__init__()
        self.itc = itc

        if not songs:
            self.add_item(discord.ui.Button(
                label='No songs found',
                style=discord.ButtonStyle.secondary,
                disabled=True
            ))
            return
        self.list = ListPlay(
            songs, row=0,
            view = self,
            )
        self.add_item(self.list, )

    async def on_timeout(self):
        await self.itc.delete_original_response()

class SongSearchList(discord.ui.View):
    def __init__(
            self,
            itc: discord.Interaction, songs: list[YTDLSource],
            manual_title: str = None,
            play: bool = False,
            playlist: m.Playlist = None
        ):
        super().__init__()
        self.itc = itc

        if not songs:
            self.add_item(discord.ui.Button(
                label='No songs found',
                style=discord.ButtonStyle.secondary,
                disabled=True
            ))
            return
        self.list = ListPlay(
            songs, row=0,
            view = self,
            manual_title=manual_title,
            play=play,
            playlist=playlist
            )
        self.add_item(self.list, )

    async def on_timeout(self):
        await self.itc.delete_original_response()
