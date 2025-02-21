import discord

from .. import models as m


class SongItem(discord.ui.Button):
    def __init__(self, song: m.YTSong):
        super().__init__(label=song.title)
        self.song = song

    async def callback(self, itc: discord.Interaction):
        print('clicked', self.song.title)
        fav = await self.song.favorite_toggle(server=itc.guild, user=itc.user)
        if fav:
            self.style = discord.ButtonStyle.gray
        else:
            self.style = discord.ButtonStyle.success

class SongListView(discord.ui.View):
    def __init__(self, user: discord.Member, items: list[m.YTSong]):
        super().__init__()

        for item in items:
            self.add_item(SongItem(item))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True