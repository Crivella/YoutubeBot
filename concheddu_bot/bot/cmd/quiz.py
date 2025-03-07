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
    async def start_quiz(self, itc: discord.Interaction, num_songs: int = 10, num_choices: int = 5):
        """Start a quiz: select atleast 1 user. The number of songs will be adjusted down
        in order to have the same number of questions for each user.

        Args:
            itc (discord.Interaction): _description_
            num_songs (int, optional): Number of questions. Defaults to 10.
            num_choices (int, optional): Number of choices. Defaults to 5.
        """
        logger.info(f'Command `start_quiz` called by `{itc.user.name}` [{itc.guild.name}]')
        playlists = await m.Playlist.get_playlists(itc=itc)
        view = v.QuizStarter(itc, playlists=playlists, num_songs=num_songs, num_choices=num_choices)
        await safe_response(itc, 'Starting quiz', view=view, ephemeral=True)
