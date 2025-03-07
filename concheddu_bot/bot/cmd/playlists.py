"""Music commands for the bot"""
import discord
import logging

from discord import app_commands
from discord.ext import commands

from ...import models as m
from .. import views as v

logger = logging.getLogger('bot')

class Playlists(commands.Cog):
    """Play command"""
    @app_commands.command()
    async def list_songs(self, itc: discord.Interaction, num: int = 20, sorting: str = 'times_played'):
        """Generate a list of songs already known to the bot

        Args:
            num (int, optional): Number of songs to list. Defaults to 20.
            sorting (str, optional): Sorting option. Defaults to 'times_played'.
        """
        logger.info(f'Command `list_songs` called with num={num}, sorting={sorting} by `{itc.user.name}` [{itc.guild.name}]')
        guild = itc.guild
        server = await m.DiscordServer.from_discord_guild(guild)
        if sorting not in m.YTSong.sort_map:
            await itc.response.send_message(
                'Invalid sorting option',
                ephemeral=True
            )
            return
        songs = await m.YTSong.get_all_songs(server=server, n=num, sorting=sorting)
        view = v.SongList(itc, songs)
        await itc.response.send_message(
            'Select a song to play',
            view=view,
            ephemeral=True
        )
        await view.list.go_to_page(0)

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
        logger.info(f'Command `create_playlist` called with name={name} by `{itc.user.name}` [{itc.guild.name}]')
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        user = await m.DiscordUser.from_discord_user(itc.user)
        songs = await m.YTSong.get_all_songs(server=server,sorting='times_played')
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
        await view.list.go_to_page(0)

    @app_commands.command()
    async def list_playlists(self, itc: discord.Interaction):
        """List the playlists"""
        logger.info(f'Command `list_playlists` called by `{itc.user.name}` [{itc.guild.name}]')
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
        logger.info(f'Command `load_playlist` called with name={name} by `{itc.user.name}` [{itc.guild.name}]')
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
        duration = await playlist.get_duration()
        await itc.response.send_message(
            f'Loaded playlist `{name}` with {len(songs)} songs duration={duration} s',
            ephemeral=True,
            delete_after=duration
        )

        for song in songs:
            await song.play(itc=itc)

    @load_playlist.autocomplete('name')
    async def _load_playlist_name(self, itc: discord.Interaction, current: str):
        """Autocomplete the playlist name"""
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        user = await m.DiscordUser.from_discord_user(itc.user)
        playlists = [p async for p in m.Playlist.objects.filter(server=server, owner=user, name__startswith=current)]
        return [app_commands.Choice(name=p.name, value=p.name) for p in playlists]
