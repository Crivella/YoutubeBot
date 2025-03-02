"""Music commands for the bot"""
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands

from ... import models as m
from ...youtube import AUDIO_DIR

logger = logging.getLogger('bot')

class ServerUtils(commands.Cog):
    """Play command"""
    def __init__(self, *args, bot, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot

    @app_commands.command()
    async def sync(self, itc: discord.Interaction):
        """Sync the bot commands"""
        logging.info(f'Command `sync` called by `{itc.user.name}` [{itc.guild.name}]')
        fmt = await self.bot.tree.sync(guild=itc.guild)

        for cmd in fmt:
            logging.debug(f'Synced {cmd} commands')

        await itc.response.send_message(f'Synced {fmt} commands')

    @app_commands.command()
    async def sync_files(self, itc: discord.Interaction):
        """Sync the bot commands"""
        logging.info(f'Command `sync_files` called by `{itc.user.name}` [{itc.guild.name}]')
        files = os.listdir(AUDIO_DIR)

        await itc.response.send_message(f'Syncing {len(files)} songs', ephemeral=True)
        for file in files:
            path = os.path.join(AUDIO_DIR, file)
            if not os.path.isfile(path):
                continue
            name, ext = os.path.splitext(file)

            await m.YTSong.from_youtube_id(name, server=itc.guild, user=itc.user)

        await itc.edit_original_response(content=f'Synced {len(files)} songs ... DONE')
