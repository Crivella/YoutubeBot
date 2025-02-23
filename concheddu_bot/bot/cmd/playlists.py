"""Music commands for the bot"""
import discord

from discord import app_commands
from discord.ext import commands

from ...import models as m
from .. import views as v
from ..utils import get_vc_from_interaction

class Playlists(commands.Cog):
    """Play command"""
    # @app_commands.command()
    # async def list_songs(self, itc: discord.Interaction, favorite: bool = False):
    #     """List the songs in the database

    #     Args:
    #         itc (discord.Interaction): _description_
    #         favorite (bool, optional): If true show song you added to favorites. Defaults to False.
    #     """
    #     guild = itc.guild
    #     server = await m.DiscordServer.from_discord_guild(guild)
    #     if favorite:
    #         user = await m.DiscordUser.from_discord_user(itc.user)
    #         songs = await user.get_favorite_songs(server=server)
    #     else:
    #         songs = await server.get_all_songs()
    #     res = []
    #     for i,song in enumerate(songs):
    #         res.append(f'**`{i:>4d}`** {song.title.strip()}')
    #     queue_str = '\n'.join(res)
    #     embedVar = discord.Embed(color=0xFF0000)
    #     embedVar.add_field(name='Songs:', value=queue_str)
    #     await itc.response.send_message(embed=embedVar, ephemeral=True)

    # @app_commands.command()
    # async def list_songs2(self, itc: discord.Interaction, favorite: bool = False):
    #     """List the songs in the database

    #     Args:
    #         itc (discord.Interaction): _description_
    #         favorite (bool, optional): If true show song you added to favorites. Defaults to False.
    #     """
    #     user = itc.user
    #     guild = itc.guild
    #     server = await m.DiscordServer.from_discord_guild(guild)
    #     user = await m.DiscordUser.from_discord_user(itc.user)
    #     favs = await user.get_favorite_songs(server=guild)

    #     songs = favs if favorite else await server.get_all_songs()

    #     if not songs:
    #         await itc.response.send_message(
    #             'No songs found',
    #             ephemeral=True
    #         )
    #         return

    #     view = v.SongListView(itc=itc)
    #     for song in songs:
    #         view.add_song(song, song in favs)
    #     # embedVar = discord.Embed(color=0xFF0000)
    #     # embedVar.add_field(name='Songs:', value='Click on the songs to toggle favorites')
    #     await itc.response.send_message(
    #         view=view, ephemeral=True,
    #         # embed=embedVar
    #     )

    @app_commands.command()
    async def list_songs(self, itc: discord.Interaction, num: int = 20, sorting: str = 'times_played'):
        """Generate a list of songs already known to the bot

        Args:
            num (int, optional): Number of songs to list. Defaults to 20.
            sorting (str, optional): Sorting option. Defaults to 'times_played'.
        """
        guild = itc.guild
        server = await m.DiscordServer.from_discord_guild(guild)
        if sorting not in m.YTSong.sort_map:
            await itc.response.send_message(
                'Invalid sorting option',
                ephemeral=True
            )
            return
        songs = await m.YTSong.get_all_songs(server=server, n=num, sorting=sorting)
        for song in songs:
            song.times_played_ = await song.get_times_played(server=server)
        view = v.SongList(itc, songs)
        await itc.response.send_message(
            'Select a song to play',
            view=view,
            ephemeral=True
        )
    @list_songs.autocomplete('sorting')
    async def _list_songs_sorting(self, itc: discord.Interaction, current: str):
        """Autocomplete the sorting option"""
        return [
            app_commands.Choice(name=m.YTSong.sort_desc[k], value=k) for k in m.YTSong.sort_map.keys()
            if k.startswith(current)
        ]

    @app_commands.command()
    async def create_playlist(self, itc: discord.Interaction, name: str):
        """Create a playlist"""
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        user = await m.DiscordUser.from_discord_user(itc.user)
        songs = await server.get_all_songs()
        if await m.Playlist.objects.filter(server=server, name=name, owner=user).aexists():
            await itc.response.send_message(
                'Playlist already exists',
                ephemeral=True,
                delete_after=10
            )
            return
        view = v.CreatePlaylist(itc, songs, name)
        await itc.response.send_message(
            'Enter the name of the playlist',
            view=view,
            ephemeral=True
        )

    @app_commands.command()
    async def list_playlists(self, itc: discord.Interaction):
        """List the playlists"""
        guild = itc.guild
        server = await m.DiscordServer.from_discord_guild(guild)
        playlists = [p async for p in m.Playlist.objects.filter(server=server)]
        res = []
        for i,playlist in enumerate(playlists):
            name = playlist.name.strip()
            cnt = await playlist.get_song_count()
            duration = await playlist.get_duration()
            res.append(f'**`{i:>4d}`** {name} ({cnt} songs) [{duration} s]')
        queue_str = '\n'.join(res)
        embedVar = discord.Embed(color=0xFF0000)
        embedVar.add_field(name='Playlists:', value=queue_str)
        await itc.response.send_message(embed=embedVar, ephemeral=True)

    @app_commands.command()
    async def load_playlist(self, itc: discord.Interaction, name: str):
        """Load a playlist"""
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        try:
            playlist = await m.Playlist.objects.aget(server=server, name=name)
        except m.Playlist.DoesNotExist:
            await itc.response.send_message(
                f'Playlist `{name}` not found',
                ephemeral=True,
                delete_after=10
            )
            return
        songs = await playlist.get_songs()
        # print(songs)
        await itc.response.send_message(
            f'Loaded playlist `{name}`',
            ephemeral=True
        )

        vc = await get_vc_from_interaction(itc)
        for song in songs:
            await song.play(vc, user=itc.user, server=server)

    @load_playlist.autocomplete('name')
    async def _load_playlist_name(self, itc: discord.Interaction, current: str):
        """Autocomplete the playlist name"""
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        user = await m.DiscordUser.from_discord_user(itc.user)
        playlists = [p async for p in m.Playlist.objects.filter(server=server, owner=user, name__startswith=current)]
        return [app_commands.Choice(name=p.name, value=p.name) for p in playlists]
