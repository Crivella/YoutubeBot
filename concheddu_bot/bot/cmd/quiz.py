"""Run quizzes for the bot."""

import discord
import logging

from discord import app_commands
from discord.ext import commands

from ...import models as m
from .utils import sanitize_ffmpeg_filter
from ..utils import sense_check, safe_response, ensure_response
from .. import views as v

logger = logging.getLogger('bot')

ALLOWED_SEGMENT_MODES = ['start', 'end', 'random']
SEGMENT_MODES_DESC = {
    'start': 'Start of the song',
    'end': 'End of the song',
    'random': 'Random segment of the song'
}

class Quiz(commands.Cog):
    """Quiz commands"""

    @app_commands.command()
    @sense_check
    @ensure_response()
    async def start_quiz(
            self, itc: discord.Interaction,
            num_songs: int = 5,
            num_choices: int = 5,
            segment_length: int = 20,
            segment_mode: str = 'start',
            audio_filter: str = None
        ):
        """Start a quiz: select atleast 1 user. The number of songs will be adjusted down
        in order to have the same number of questions for each user.

        Args:
            num_songs (int, optional): Number of questions per user. Defaults to 5.
            num_choices (int, optional): Number of choices. Defaults to 5.
            segment_length (int, optional): Length of the segment of the song to play. Defaults to 20.
            segment_mode (str, optional): start/end/random. Defaults to 'start'.
            audio_filter (str, optional): FFMPEG audio filter to apply. Defaults to None.
        """
        logger.info(f'Command `start_quiz` called by `{itc.user.name}` [{itc.guild.name}]')
        if num_songs < 1:
            await safe_response(itc, 'Number of songs must be greater than 0', ephemeral=True)
            return
        if num_choices < 2:
            await safe_response(itc, 'Number of choices must be greater than 1', ephemeral=True)
            return
        if segment_length < 1:
            await safe_response(itc, 'Segment length must be greater than 0', ephemeral=True)
            return
        if segment_mode not in ALLOWED_SEGMENT_MODES:
            await safe_response(itc, f'Segment mode invalid', ephemeral=True)
            return
        playlists = await m.Playlist.get_playlists(itc=itc)
        audio_filter = sanitize_ffmpeg_filter(audio_filter)
        view = v.QuizSongs(
            itc, playlists=playlists,
            num_songs=num_songs, num_choices=num_choices,
            segment_length=segment_length, segment_mode=segment_mode,
            audio_filter=audio_filter
        )
        await safe_response(itc, 'Starting quiz', view=view, ephemeral=True)
    @start_quiz.autocomplete('segment_mode')
    async def _autocomplete_segment_mode(self, itc: discord.Interaction, current: str):
        """Autocomplete the segment mode"""
        return [
            app_commands.Choice(name=SEGMENT_MODES_DESC[k], value=k) for k in ALLOWED_SEGMENT_MODES
            if k.startswith(current)
        ]
