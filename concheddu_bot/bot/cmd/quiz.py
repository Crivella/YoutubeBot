"""Run quizzes for the bot."""
import asyncio
import discord
import logging

from discord import app_commands
from discord.ext import commands

from ...import models as m
from .utils import sanitize_ffmpeg_filter
from ..utils import sense_check, safe_response, ensure_response, SenseCheckError
from .. import views as v
from .utils import call_command_register
from . import transformers as tfs

logger = logging.getLogger('bot')

ALLOWED_SEGMENT_MODES = ['start', 'end', 'random']
SEGMENT_MODES_DESC = {
    'start': 'Start of the song',
    'end': 'End of the song',
    'random': 'Random segment of the song'
}

current_quiz: dict[int, v.QuizSongs] = {}

class QuizSong(commands.GroupCog, group_name='quiz_song'):
    """Quiz commands"""

    @app_commands.command()
    @ensure_response(allowed_exceptions=[SenseCheckError])
    @call_command_register()
    @sense_check
    async def start(
            self, itc: discord.Interaction,
            num_songs: app_commands.Transform[int, tfs.IntRangeTransformer(min=1)] = 5,
            num_choices: app_commands.Transform[int, tfs.IntRangeTransformer(min=2)] = 5,
            segment_length: app_commands.Transform[int, tfs.IntRangeTransformer(min=1)] = 20,
            segment_mode: str = 'start',
            audio_filter: str = None,
            multiple_choice: bool = True,
            show_thumbnail: bool = False
        ):
        """Start a quiz: select atleast 1 user. The number of songs will be adjusted down
        in order to have the same number of questions for each user.

        Args:
            num_songs (int, optional): Number of questions per user. Defaults to 5.
            num_choices (int, optional): Number of choices/song pool (multiplechoise/non). Defaults to 5.
            segment_length (int, optional): Length of the segment of the song to play. Defaults to 20.
            segment_mode (str, optional): start/end/random. Defaults to 'start'.
            audio_filter (str, optional): FFMPEG audio filter to apply. Defaults to None.
            multiple_choice (bool, optional): Multiple choice or use command to answer. Defaults to True.
            show_thumbnail (bool, optional): Show thumbnail in the quiz. Defaults to False.
        """
        if segment_mode not in ALLOWED_SEGMENT_MODES:
            await safe_response(itc, f'Segment mode invalid', ephemeral=True)
            return
        server_id = itc.guild.id
        if server_id in current_quiz:
            await safe_response(itc, 'Quiz already ongoing', ephemeral=True)
            return
        if multiple_choice and num_choices > 20:
            await safe_response(itc, 'Too many choices for multiple choice quiz (max 20)', ephemeral=True)
            return
        playlists = await m.Playlist.get_playlists(itc=itc)
        audio_filter = sanitize_ffmpeg_filter(audio_filter)
        current_quiz[server_id] = view = v.QuizSongs(
            itc,

            playlists=playlists,
            num_songs=num_songs,
            num_choices=num_choices,

            segment_length=segment_length,
            segment_mode=segment_mode,
            audio_filter=audio_filter,

            multiple_choice=multiple_choice,
            show_thumbnail=show_thumbnail
        )
        if not multiple_choice:
            async def start_callback(songs: list[m.YTSong], all_songs: list[m.YTSong], quiz: m.QuizSong):
                tfs.SongTransformer.register_server_playlist(server_id, all_songs)
            view.on_start.append(start_callback)
        async def finish_callback():
            tfs.SongTransformer.remove_server_playlist(server_id)
            current_quiz.pop(server_id, None)
        view.on_finish.append(finish_callback)
        await safe_response(itc, 'Starting quiz', view=view, ephemeral=True)
    @start.autocomplete('segment_mode')
    async def _autocomplete_segment_mode(self, itc: discord.Interaction, current: str):
        """Autocomplete the segment mode"""
        return [
            app_commands.Choice(name=SEGMENT_MODES_DESC[k], value=k) for k in ALLOWED_SEGMENT_MODES
            if k.startswith(current)
        ]

    @app_commands.command()
    @ensure_response()
    @call_command_register()
    async def list(self, itc: discord.Interaction):
        """List the quizzes"""
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        q = m.QuizSong.objects
        q = q.filter(server=server)
        q = q.order_by('-date_start')
        quizes = [quiz async for quiz in q.all()]
        view = v.QuizSongsList(itc, quizes)
        await safe_response(itc, 'Select a quiz to play', view=view, ephemeral=True)


    @app_commands.command()
    @ensure_response()
    @call_command_register()
    async def answer(
            self, itc: discord.Interaction,
            song: app_commands.Transform[m.YTSong, tfs.SongTransformer(from_server_playlist=True)]
            ):
        """List the quizzes"""
        quiz = current_quiz.get(itc.guild.id, None)
        if quiz is None:
            await safe_response(itc, 'No quiz started', ephemeral=True)
            return
        await quiz.command_answer(itc, song)
        await safe_response(itc, 'Answered', ephemeral=True)
        await asyncio.sleep(1)
        await itc.delete_original_response()

    @app_commands.command()
    @ensure_response()
    @call_command_register()
    async def stop(self, itc: discord.Interaction):
        """Stop the quiz"""
        quiz = current_quiz.get(itc.guild.id, None)
        if quiz is None:
            await safe_response(itc, 'No quiz started', ephemeral=True)
            return
        await quiz.quiz_finish()
        await safe_response(itc, 'Quiz stopped', ephemeral=True)
