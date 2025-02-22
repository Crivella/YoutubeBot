"""Music commands for the bot"""
import discord

from discord import app_commands
from discord.ext import commands

from ...import models as m
from ..views import SongListView

class Playlists(commands.Cog):
    """Play command"""
    @app_commands.command()
    async def list_songs(self, itc: discord.Interaction, favorite: bool = False):
        """List the songs in the database

        Args:
            itc (discord.Interaction): _description_
            favorite (bool, optional): If true show song you added to favorites. Defaults to False.
        """
        guild = itc.guild
        server = await m.DiscordServer.from_discord_guild(guild)
        if favorite:
            user = await m.DiscordUser.from_discord_user(itc.user)
            songs = await user.get_favorite_songs(server=server)
        else:
            songs = await server.get_all_songs()
        res = []
        for i,song in enumerate(songs):
            res.append(f'**`{i:>4d}`** {song.title.strip()}')
        queue_str = '\n'.join(res)
        embedVar = discord.Embed(color=0xFF0000)
        embedVar.add_field(name='Songs:', value=queue_str)
        await itc.response.send_message(embed=embedVar, ephemeral=True)

    @app_commands.command()
    async def list_songs2(self, itc: discord.Interaction, favorite: bool = False):
        """List the songs in the database

        Args:
            itc (discord.Interaction): _description_
            favorite (bool, optional): If true show song you added to favorites. Defaults to False.
        """
        user = itc.user
        guild = itc.guild
        server = await m.DiscordServer.from_discord_guild(guild)
        user = await m.DiscordUser.from_discord_user(itc.user)
        favs = await user.get_favorite_songs(server=guild)

        songs = favs if favorite else await server.get_all_songs()

        if not songs:
            await itc.response.send_message(
                'No songs found',
                ephemeral=True
            )
            return

        view = SongListView(itc=itc)
        for song in songs:
            view.add_song(song, song in favs)
        # embedVar = discord.Embed(color=0xFF0000)
        # embedVar.add_field(name='Songs:', value='Click on the songs to toggle favorites')
        await itc.response.send_message(
            view=view, ephemeral=True,
            # embed=embedVar
        )
