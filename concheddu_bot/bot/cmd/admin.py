"""Music commands for the bot"""
import asyncio
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands

from ... import models as m
from ...youtube import AUDIO_DIR
from ..utils import ensure_response, safe_response
from . import transformers as tfs
from .utils import call_command_register

logger = logging.getLogger('bot')

ADMIN_ID = int(os.getenv('BOT_ADMIN_ID', -1))

async def loop_process(itc: discord.Interaction, aiter, get_coro, delay: int = None):
    """Run a coroutine on an async iterator"""
    cnt = 0
    async for item in aiter:
        await get_coro(itc, item)
        if delay:
            await asyncio.sleep(delay)
        cnt += 1
        if cnt % 10 == 0:
            await safe_response(itc, f'Processed {cnt} items', ephemeral=True)

class Admin(commands.GroupCog, group_name='admin'):
    """Play command"""
    def __init__(self, *args, bot, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot

    @app_commands.command()
    @app_commands.check(lambda itc: itc.user.id == ADMIN_ID)
    @ensure_response()
    @call_command_register()
    async def sync(self, itc: discord.Interaction):
        """Sync the bot commands"""
        fmt = await self.bot.tree.sync(guild=itc.guild)

        for cmd in fmt:
            logger.debug(f'Synced {cmd} commands')

        await itc.response.send_message(f'Synced {fmt} commands', ephemeral=True)

    @app_commands.command()
    @app_commands.check(lambda itc: itc.user.id == ADMIN_ID)
    @ensure_response()
    @call_command_register()
    async def download_all_thumbnails(self, itc: discord.Interaction):
        """Download all thumbnails"""
        await safe_response(itc, f'Downloading all thumbnails', ephemeral=True)
        await loop_process(
            itc,
            m.YTSong.objects.all(),
            lambda _, song: song.download_thumbnails(),
            delay=1
            )

    @app_commands.command()
    @app_commands.check(lambda itc: itc.user.id == ADMIN_ID)
    @ensure_response()
    @call_command_register()
    async def get_thumb_urls(self, itc: discord.Interaction):
        """Download all thumbnails"""
        await safe_response(itc, f'Getting all thumbnail urls', ephemeral=True)
        await loop_process(
            itc,
            m.YTSong.objects.all(),
            lambda _, song: song.get_thumbnails_urls(),
            delay=1
            )

    @app_commands.command()
    @app_commands.check(lambda itc: itc.user.id == ADMIN_ID)
    @ensure_response()
    @call_command_register()
    async def sync_files_to_db(self, itc: discord.Interaction):
        """Add files present on the device to songs in the database"""
        files = os.listdir(AUDIO_DIR)
        await safe_response(itc, f'Ensuring all files correspond to a song', ephemeral=True)

        for file in files:
            path = os.path.join(AUDIO_DIR, file)
            if not os.path.isfile(path):
                continue
            name, _ = os.path.splitext(file)

            song = await m.YTSong.from_youtube_id(name)
            if song:
                user = await m.DiscordUser.from_discord_user(itc.user)
                server = await m.DiscordServer.from_discord_guild(itc.guild)
                await server.add_song(song=song, user=user)
            await song.get_source()

        await safe_response(itc, f'Synced {len(files)} songs ... DONE', ephemeral=True)

    @app_commands.command()
    @app_commands.check(lambda itc: itc.user.id == ADMIN_ID)
    @ensure_response()
    @call_command_register()
    async def sync_db_to_files(self, itc: discord.Interaction):
        """Ensure all entries in the database have a corresponding file"""
        await safe_response(itc, f'Ensuring all songs are downloaded/normailzed', ephemeral=True)
        async for song in m.YTSong.objects.all():
            await song.get_source()

    @app_commands.command()
    @app_commands.check(lambda itc: itc.user.id == ADMIN_ID)
    @ensure_response()
    @call_command_register()
    async def delete_song(
            self, itc: discord.Interaction,
            song:app_commands.Transform[m.YTSong, tfs.SongTransformer],
            delete_files: bool = True
        ):
        """Delete a song

        Args:
            song (str): An existing song
            delete_files (bool, optional): Whether to delete the files associated with the song. Defaults to True.
        """
        if delete_files:
            await song.delete_files()

        await song.adelete()
        await safe_response(itc, f'Deleted song `{song.title}`', ephemeral=True)
