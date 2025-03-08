import discord

from ... import models as m
from .buttons import CallbackButton
from .paged import ListPlay


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
