"""Music commands for the bot"""
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands

from ... import models as m
from ...youtube import AUDIO_DIR
from ..utils import ensure_response, safe_response

logger = logging.getLogger('bot')

async def autocomplete_songs_sorting(self, itc: discord.Interaction, current: str):
    """Autocomplete the sorting option"""
    return [
        app_commands.Choice(name=m.YTSong.sort_desc[k], value=k) for k in m.YTSong.sort_map.keys()
        if k.startswith(current)
    ]

async def autocomplete_playlist_name(self, itc: discord.Interaction, current: str):
    """Autocomplete the playlist name"""
    server = await m.DiscordServer.from_discord_guild(itc.guild)
    user = await m.DiscordUser.from_discord_user(itc.user)
    # playlists = [p async for p in m.Playlist.objects.filter(server=server, owner=user, name__startswith=current)]
    playlists = [p async for p in m.Playlist.objects.filter(server=server, name__startswith=current)]
    return [app_commands.Choice(name=p.name, value=p.name) for p in playlists]

class ServerUtils(commands.Cog):
    """Play command"""
    def __init__(self, *args, bot, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot

    @app_commands.command()
    @ensure_response()
    async def sync(self, itc: discord.Interaction):
        """Sync the bot commands"""
        logging.info(f'Command `sync` called by `{itc.user.name}` [{itc.guild.name}]')
        fmt = await self.bot.tree.sync(guild=itc.guild)

        for cmd in fmt:
            logging.debug(f'Synced {cmd} commands')

        await itc.response.send_message(f'Synced {fmt} commands')

    @app_commands.command()
    @ensure_response()
    async def sync_files(
            self, itc: discord.Interaction,
            songs: bool = False, files: bool = True
        ):
        """Sync the bot commands

        Args:
            songs (bool, optional): Ensure all song sources are downloaded and normalized. Defaults to False.
            files (bool, optional): Ensure song files are also present in the database. Defaults to True.
        """
        logging.info(f'Command `sync_files` called by `{itc.user.name}` [{itc.guild.name}]')
        files = os.listdir(AUDIO_DIR)

        if songs:
            await safe_response(itc, f'Ensuring all songs are downloaded/normailzed', ephemeral=True)
            async for song in m.YTSong.objects.all():
                await song.get_source()

        if files:
            await safe_response(itc, f'Ensuring all files correspond to a song', ephemeral=True)

            for file in files:
                path = os.path.join(AUDIO_DIR, file)
                if not os.path.isfile(path):
                    continue
                name, ext = os.path.splitext(file)

                song = await m.YTSong.from_youtube_id(name, server=itc.guild, user=itc.user)
                await song.get_source()

            await safe_response(itc, f'Synced {len(files)} songs ... DONE', ephemeral=True)
