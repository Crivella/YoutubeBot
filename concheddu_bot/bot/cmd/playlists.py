"""Music commands for the bot"""
import discord
import logging

from discord import app_commands
from discord.ext import commands

from ...import models as m
from .. import views as v
from .utils import PlaylistTransformer, SongFilterTransformer
from ..utils import ensure_response, sense_check

logger = logging.getLogger('bot')

class Playlists(commands.GroupCog, group_name='playlists'):
    """Play command"""
    @app_commands.command()
    @ensure_response()
    async def create(
        self, itc: discord.Interaction,
        name: str,
        sorting: app_commands.Transform[str, SongFilterTransformer] = 'times_played',
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
        await itc.response.send_message(
            f'Editing playlist `{name}`',
            view=view,
            ephemeral=True
        )
        await view.list.go_to_page(0)

    @app_commands.command()
    @ensure_response()
    async def delete(
            self,
            itc: discord.Interaction,
            playlist: app_commands.Transform[m.Playlist, PlaylistTransformer],
        ):
        """Delete a playlist by name

        Args:
            name (str): The name of the playlist
        """
        logger.info(f'Command `delete_playlist` called by `{itc.user.name}` [{itc.guild.name}]')
        if playlist is None:
            await itc.response.send_message(
                f'Playlist not found',
                ephemeral=True,
                delete_after=10
            )
            return
        view = v.DeletePlaylist(itc, playlist)
        duration = await playlist.get_duration()
        num_songs = await playlist.get_song_count()
        msg = f'Are you sure you want to delete the playlist `{playlist.name}` with {num_songs} songs and duration={duration} s?'
        await itc.response.send_message(
            msg,
            view=view,
            ephemeral=True
        )

    @app_commands.command()
    @ensure_response()
    async def list(self, itc: discord.Interaction):
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
    async def load(
            self, itc: discord.Interaction,
            playlist: app_commands.Transform[m.Playlist, PlaylistTransformer],
            num: int = 0,
            sorting: app_commands.Transform[str, SongFilterTransformer] = 'times_played',
            ):
        """Load a playlist

        Args:
            name (str): The name of the playlist
            num (int, optional): The number of songs to load. Defaults to 0 (all).
            sorting (str, optional): Sorting option. Defaults to 'times_played'.
        """
        logger.info(f'Command `load_playlist` called by `{itc.user.name}` [{itc.guild.name}]')
        if playlist is None:
            await itc.response.send_message(
                f'Playlist not found',
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
            f'Loaded playlist `{playlist.name}` with {len(songs)} songs duration={duration} s',
            ephemeral=True,
            delete_after=duration
        )

        for song in songs:
            await song.play(itc=itc)

    @app_commands.command()
    @ensure_response(before=True, defer=True)
    async def edit(
            self, itc: discord.Interaction,
            playlist: app_commands.Transform[m.Playlist, PlaylistTransformer],
            rename_to: str = None,
            sorting: app_commands.Transform[str, SongFilterTransformer] = 'times_played',
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
        logger.info(f'Command `edit_playlist` called with by `{itc.user.name}` [{itc.guild.name}]')
        server = await m.DiscordServer.from_discord_guild(itc.guild)

        if playlist is None:
            await itc.response.send_message(
                f'Playlist not found',
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
