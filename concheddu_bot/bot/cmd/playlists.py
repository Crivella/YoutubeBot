"""Music commands for the bot"""
import discord
import logging

from discord import app_commands
from discord.ext import commands

from ...import models as m
from .. import views as v
from .utils import autocomplete_playlist_name, autocomplete_songs_sorting
from ..utils import ensure_response, sense_check, safe_defer, safe_response

logger = logging.getLogger('bot')

class Playlists(commands.Cog):
    """Play command"""
    @app_commands.command()
    @ensure_response(before=True, defer=True)  # Defer to avoid timeout
    async def list_songs(
            self, itc: discord.Interaction,
            num: int = 100, sorting: str = 'times_played',
            filter_title: str = None,
            ascending: bool = None
        ):
        """Generate a list of songs already known to the bot

        Args:
            num (int, optional): Number of songs to list. Defaults to 100.
            sorting (str, optional): Sorting option. Defaults to 'times_played'.
            filter_title (str, optional): Filter the songs by title. Defaults to None.
            ascending (bool, optional): Sort in ascending order. Defaults to server auto-detect.
        """
        logger.info(f'Command `list_songs` called with num={num}, sorting={sorting} by `{itc.user.name}` [{itc.guild.name}]')
        guild = itc.guild
        server = await m.DiscordServer.from_discord_guild(guild)
        songs = await m.YTSong.get_all_songs(
            server=server, n=num, sorting=sorting,
            filter_title=filter_title,
            asc=ascending
            )
        view = v.SongList(itc, songs)
        await safe_response(
            itc,
            'Select a song to play',
            view=view,
            ephemeral=True
        )
        await view.list.go_to_page(0)
    @list_songs.autocomplete('sorting')
    async def _list_songs_sorting(self, itc: discord.Interaction, current: str):
        """Autocomplete the sorting option"""
        return await autocomplete_songs_sorting(self, itc, current)

    @app_commands.command()
    @ensure_response()
    async def create_playlist(
        self, itc: discord.Interaction,
        name: str,
        sorting: str = 'times_played',
        filter_title: str = None,
        ascending: bool = None
        ):
        """Create a playlist

        Args:
            name (str): The name of the playlist
            sorting (str, optional): Sorting option. Defaults to 'times_played'.
            filter_title (str, optional): Filter the songs by title. Defaults to None.
            ascending (bool, optional): Sort in ascending order. Defaults to server auto-detect.
        """
        logger.info(f'Command `create_playlist` called with name={name} by `{itc.user.name}` [{itc.guild.name}]')
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        user = await m.DiscordUser.from_discord_user(itc.user)
        songs = await m.YTSong.get_all_songs(
            server=server, sorting=sorting,
            filter_title=filter_title,
            asc=ascending
            )
        if await m.Playlist.objects.filter(server=server, name=name, owner=user).aexists():
            await itc.response.send_message(
                'Playlist already exists',
                ephemeral=True,
                delete_after=10
            )
            return
        playlist = await m.Playlist.create_playlist(server=server, name=name, user=user)
        view = v.EditPlaylist(itc, playlist, songs)
        # view = v.CreatePlaylist(itc, songs, name)
        await itc.response.send_message(
            f'Editing playlist `{name}`',
            view=view,
            ephemeral=True
        )
        await view.list.go_to_page(0)
    @create_playlist.autocomplete('sorting')
    async def _create_playlist_sorting(self, itc: discord.Interaction, current: str):
        """Autocomplete the sorting option"""
        return await autocomplete_songs_sorting(self, itc, current)

    @app_commands.command()
    @ensure_response()
    async def delete_playlist(self, itc: discord.Interaction, name: str):
        """Delete a playlist by name

        Args:
            name (str): The name of the playlist
        """
        logger.info(f'Command `delete_playlist` called with name={name} by `{itc.user.name}` [{itc.guild.name}]')
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        user = await m.DiscordUser.from_discord_user(itc.user)
        try:
            playlist = await m.Playlist.objects.aget(server=server, name=name, owner=user)
        except m.Playlist.DoesNotExist:
            await itc.response.send_message(
                f'Playlist `{name}` not found',
                ephemeral=True,
                delete_after=10
            )
            return
        view = v.DeletePlaylist(itc, playlist)
        duration = await playlist.get_duration()
        num_songs = await playlist.get_song_count()
        msg = f'Are you sure you want to delete the playlist `{name}` with {num_songs} songs and duration={duration} s?'
        await itc.response.send_message(
            msg,
            view=view,
            ephemeral=True
        )
    @delete_playlist.autocomplete('name')
    async def _delete_playlist_name(self, itc: discord.Interaction, current: str):
        """Autocomplete the playlist name"""
        return await autocomplete_playlist_name(self, itc, current, enforce_user=True)

    @app_commands.command()
    @ensure_response()
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
            hh = duration // 3600
            mm = (duration % 3600) // 60
            ss = duration % 60
            duration = f'{hh:02d}:{mm:02d}:{ss:02d}'
            res.append(f'**`{i:>4d}`** {name} ({cnt} songs) [{duration}]')
        queue_str = '\n'.join(res)
        embedVar = discord.Embed(color=0xFF0000)
        embedVar.add_field(name='Playlists:', value=queue_str)
        await itc.response.send_message(embed=embedVar, ephemeral=True)

    @app_commands.command()
    @sense_check
    @ensure_response()
    async def load_playlist(
            self, itc: discord.Interaction,
            name: str, num: int = 0,
            sorting: str = 'times_played'
            ):
        """Load a playlist

        Args:
            name (str): The name of the playlist
            num (int, optional): The number of songs to load. Defaults to 0 (all).
            sorting (str, optional): Sorting option. Defaults to 'times_played'.
        """
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
        if num < 0:
            await itc.response.send_message(
                'Number of songs must be positive',
                ephemeral=True,
                delete_after=10
            )
            return
        songs = await playlist.get_all_songs(n=num, sorting=sorting)
        if not songs:
            await itc.response.send_message(
                'No songs in the playlist',
                ephemeral=True,
                delete_after=10
            )
            return
        duration = sum(song.duration for song in songs)
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
        return await autocomplete_playlist_name(self, itc, current)
    @load_playlist.autocomplete('sorting')
    async def _load_playlist_sorting(self, itc: discord.Interaction, current: str):
        """Autocomplete the sorting option"""
        return await autocomplete_songs_sorting(self, itc, current)

    @app_commands.command()
    @ensure_response()
    async def edit_playlist(
            self, itc: discord.Interaction,
            name: str, rename_to: str = None, sorting: str = 'times_played',
            filter_title: str = None,
            ascending: bool = None
        ):
        """Edit a playlist

        Args:
            name (str): The name of the playlist to edit
            rename_to (str, optional): If set, rename the playlist to this name. Defaults to None.
            sorting (str, optional): Sorting option. Defaults to 'times_played'.
            filter_title (str, optional): Filter the songs by title. Defaults to None.
            ascending (bool, optional): Sort in ascending order. Defaults to server auto-detect.
        """
        logger.info(f'Command `edit_playlist` called with name={name} by `{itc.user.name}` [{itc.guild.name}]')
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        user = await m.DiscordUser.from_discord_user(itc.user)
        try:
            # playlist = await m.Playlist.objects.aget(server=server, name=name, owner=user)
            playlist = await m.Playlist.objects.aget(server=server, name=name)
        except m.Playlist.DoesNotExist:
            await itc.response.send_message(
                f'Playlist `{name}` not found',
                ephemeral=True,
                delete_after=10
            )
            return
        all_songs = await m.YTSong.get_all_songs(
            server=server, sorting=sorting,
            filter_title=filter_title,
            asc=ascending
            )
        pls_songs = await playlist.get_all_songs()
        view = v.EditPlaylist(itc, playlist, all_songs, defaults=pls_songs, new_name=rename_to)
        await itc.response.send_message(
            'Edit the playlist',
            view=view,
            ephemeral=True
        )
        await view.list.go_to_page(0)

    @edit_playlist.autocomplete('name')
    async def _edit_playlist_name(self, itc: discord.Interaction, current: str):
        """Autocomplete the playlist name"""
        return await autocomplete_playlist_name(self, itc, current)
    @edit_playlist.autocomplete('sorting')
    async def _edit_playlist_sorting(self, itc: discord.Interaction, current: str):
        """Autocomplete the sorting option"""
        return await autocomplete_songs_sorting(self, itc, current)
