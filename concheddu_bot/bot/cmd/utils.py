"""Music commands for the bot"""
import os

import discord
from discord import app_commands
from discord.ext import commands

from ... import models as m
from ...youtube import AUDIO_DIR


class ServerUtils(commands.Cog):
    """Play command"""
    def __init__(self, *args, bot, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot

    @app_commands.command()
    async def sync(self, itc: discord.Interaction):
        """Sync the bot commands"""
        fmt = await self.bot.tree.sync(guild=itc.guild)
        print(f'Synced {fmt} commands')
        await itc.response.send_message(f'Synced {fmt} commands')

    @app_commands.command()
    async def sync_files(self, itc: discord.Interaction):
        """Sync the bot commands"""
        files = os.listdir(AUDIO_DIR)

        await itc.response.send_message(f'Syncing {len(files)} songs', ephemeral=True)
        for file in files:
            path = os.path.join(AUDIO_DIR, file)
            if not os.path.isfile(path):
                continue
            name, ext = os.path.splitext(file)

            await m.YTSong.from_youtube_id(name, server=itc.guild, user=itc.user)

        await itc.edit_original_response(content=f'Synced {len(files)} songs ... DONE')
