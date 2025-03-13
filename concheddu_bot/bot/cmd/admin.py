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

ADMIN_ID = os.getenv('BOT_ADMIN_ID', -1)

class Admin(commands.GroupCog, group_name='admin'):
    """Play command"""
    def __init__(self, *args, bot, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot

    @app_commands.command()
    @app_commands.check(lambda itc: itc.user.id == ADMIN_ID)
    @ensure_response()
    async def sync(self, itc: discord.Interaction):
        """Sync the bot commands"""
        logger.info(f'Command `sync` called by `{itc.user.name}` [{itc.guild.name}]')
        fmt = await self.bot.tree.sync(guild=itc.guild)

        for cmd in fmt:
            logger.debug(f'Synced {cmd} commands')

        await itc.response.send_message(f'Synced {fmt} commands')

    @app_commands.command()
    @app_commands.check(lambda itc: itc.user.id == ADMIN_ID)
    @ensure_response()
    async def sync_files_to_db(self, itc: discord.Interaction):
        """Add files present on the device to songs in the database"""
        logging.info(f'Command `sync_files_to_db` called by `{itc.user.name}` [{itc.guild.name}]')

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

    @app_commands.command()
    @app_commands.check(lambda itc: itc.user.id == ADMIN_ID)
    @ensure_response()
    async def sync_db_to_files(self, itc: discord.Interaction):
        """Ensure all entries in the database have a corresponding file"""
        logging.info(f'Command `sync_db_to_files` called by `{itc.user.name}` [{itc.guild.name}]')

        await safe_response(itc, f'Ensuring all songs are downloaded/normailzed', ephemeral=True)
        async for song in m.YTSong.objects.all():
            await song.get_source()
