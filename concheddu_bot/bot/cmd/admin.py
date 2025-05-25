"""Music commands for the bot"""
import asyncio
import logging
import os
import sys

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
            delay=.2
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

    @app_commands.command()
    @app_commands.check(lambda itc: itc.user.id == ADMIN_ID)
    @ensure_response()
    @call_command_register()
    async def hard_restart(self, itc: discord.Interaction):
        """Restart the bot by forcing the current process to exit and the bot to restart"""
        await safe_response(itc, f'Restarting bot', ephemeral=True)
        sys.exit(0)

    @app_commands.command()
    @app_commands.check(lambda itc: itc.user.id == ADMIN_ID)
    @ensure_response()
    @call_command_register()
    async def test_parse(self, itc: discord.Interaction):
        """Restart the bot by forcing the current process to exit and the bot to restart"""
        # quizzes: list[m.QuizSong] = await m.QuizSong.objects.all()
        quizzes: list[m.QuizSong] = [
            (a.id, a.date_start, a.date_end) async for a in m.QuizSong.objects.filter(
                date_start__isnull=False,
                date_end__isnull=False
            ).all()
        ]
        # ranges = []
        # for quiz in quizzes:
        #     if quiz.date_start is None or quiz.date_end is None:
        #         continue
        #     q_str = f'QuizSong(id={quiz.id}, start={quiz.date_start}, end={quiz.date_end})'
        #     logger.info(q_str)
        #     ranges.append((quiz.date_start, quiz.date_end))
        play_events = [a async for a in m.PlayEvent.objects.all()]
        to_flag = []
        for play in play_events:
            if play.date is None:
                continue
            p_str = f'PlayEvent(id={play.id}, date={play.date})'
            for i,s,e in quizzes:
                if s <= play.date <= e:
                    p_str += f' in range {s} - {e}  for QuizSong(id={i})'
                    to_flag.append(play)
                    play.quiz_id = i
                    await play.asave()
                    break

            logger.info(p_str)
        msg = f'Found {len(quizzes)} quizzes and {len(play_events)} play events'
        msg += f'\nFinished quizzes: {len(quizzes)}'
        msg += f'\nPlay events in quizzes: {len(to_flag)}'
        await safe_response(itc, msg, ephemeral=True)
