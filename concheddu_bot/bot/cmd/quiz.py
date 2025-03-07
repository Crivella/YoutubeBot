"""Run quizzes for the bot."""

import discord
import logging

from discord import app_commands
from discord.ext import commands

from ...import models as m
from ..utils import sense_check, safe_response, ensure_response
from .. import views as v

logger = logging.getLogger('bot')

class Quiz(commands.Cog):
    """Quiz commands"""
    @app_commands.command()
    @sense_check
    @ensure_response()
    async def start_quiz(self, itc: discord.Interaction):
        """Start a quiz"""
        logger.info(f'Command `start_quiz` called by `{itc.user.name}` [{itc.guild.name}]')
        playlists = await m.Playlist.get_playlists(itc=itc)
        view = v.QuizStarter(itc, playlists=playlists)
        await safe_response(itc, 'Starting quiz', view=view, ephemeral=True)

