"""Music commands for the bot"""
import logging
import os
import re

import discord
from discord import app_commands
from discord.ext import commands

from ... import models as m
from ...models import filters as flt
from ...youtube import AUDIO_DIR
from ..utils import ensure_response, safe_response

logger = logging.getLogger('bot')

def sanitize_ffmpeg_filter(afilt: str):
    """Sanitize the ffmpeg filter"""
    rgx = re.compile(r'^[a-z0-9=_:,]+$')
    res = afilt
    res = res.replace(';', '')
    res = res.replace('|', '')
    res = res.replace('"', '')
    res = res.replace("'", '')

    if not rgx.match(res):
        logger.warning(f'Invalid ffmpeg filter: {afilt}')
        raise ValueError(f'Invalid ffmpeg filter: {afilt}')
    logger.debug(f'Sanitized ffmpeg filter: {afilt} -> {res}')

    return res


async def autocomplete_songs_sorting(self, itc: discord.Interaction, current: str):
    """Autocomplete the sorting option"""
    return [
        app_commands.Choice(name=flt.song_order_desc[k], value=k) for k in flt.song_order_map.keys()
        if k.startswith(current)
    ]

async def autocomplete_playlist_name(self, itc: discord.Interaction, current: str, enforce_user: bool = False):
    """Autocomplete the playlist name"""
    server = await m.DiscordServer.from_discord_guild(itc.guild)
    user = await m.DiscordUser.from_discord_user(itc.user)
    if enforce_user:
        playlists = [p async for p in m.Playlist.objects.filter(server=server, owner=user, name__startswith=current)]
    else:
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
        logger.info(f'Command `sync` called by `{itc.user.name}` [{itc.guild.name}]')
        fmt = await self.bot.tree.sync(guild=itc.guild)

        for cmd in fmt:
            logger.debug(f'Synced {cmd} commands')

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

        if songs:
            await safe_response(itc, f'Ensuring all songs are downloaded/normailzed', ephemeral=True)
            async for song in m.YTSong.objects.all():
                await song.get_source()

        if files:
            files = os.listdir(AUDIO_DIR)
            await safe_response(itc, f'Ensuring all files correspond to a song', ephemeral=True)

            for file in files:
                path = os.path.join(AUDIO_DIR, file)
                if not os.path.isfile(path):
                    continue
                name, ext = os.path.splitext(file)

                song = await m.YTSong.from_youtube_id(name, server=itc.guild, user=itc.user)
                await song.get_source()

            await safe_response(itc, f'Synced {len(files)} songs ... DONE', ephemeral=True)
