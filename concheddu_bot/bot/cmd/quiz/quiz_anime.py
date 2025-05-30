"""Run quizzes for the bot."""
import logging

import discord
from discord import app_commands
from discord.ext import commands

from .... import models as m
from ... import views as v
from ...utils import ensure_response, safe_response
from .. import transformers as tfs
from ..utils import call_command_register

logger = logging.getLogger('bot')

current_quiz_hl: dict[int, v.QuizHighLowRunner] = {}

class QuizAnime(commands.GroupCog, group_name='quiz_anime'):
    """Quiz commands for high/low game"""

    @app_commands.command()
    @ensure_response()
    @call_command_register()
    async def start_highlow(
            self, itc: discord.Interaction,
            object_type: app_commands.Transform[str, tfs.ObjectTypeTransformer()],
            object_param: app_commands.Transform[str, tfs.ObjectParamTransformer()],
            max_top: app_commands.Transform[int, tfs.IntRangeTransformer(min=0, max=5000)] = 0
        ):
        """Start a high/low quiz game.

        Args:
            itc (discord.Interaction): The interaction context.
            object_type (str): Must be one of the allowed object type
            object_param (str): Must be one of the allowed object param for the object type.
            max_top (int): Limit the items in the quiz to the top X items ordered by the object param.
        """
        view = v.QuizHighLowRunner(
            itc,
            object_type=object_type,
            object_param=object_param,
            max_top=max_top,
            user=itc.user
        )

        server_id = itc.guild.id
        user_id = itc.user.id

        async def start_callback(quiz: m.QuizHighLow):
            current_quiz_hl[(server_id, user_id)] = view
        view.on_start.append(start_callback)

        async def finish_callback():
            current_quiz_hl.pop((server_id, user_id), None)
        view.on_finish.append(finish_callback)

        await safe_response(itc, 'Starting high/low quiz', view=view, ephemeral=True)

    @app_commands.command()
    @ensure_response()
    @call_command_register()
    async def stop_highlow(self, itc: discord.Interaction):
        """Stop the quiz"""
        server_id = itc.guild.id
        user_id = itc.user.id
        quiz = current_quiz_hl.get((server_id, user_id), None)
        if quiz is None:
            await safe_response(itc, 'No quiz started by you', ephemeral=True)
            return
        try:
            await quiz.quiz_finish()
        except Exception as e:
            logger.exception('Error stopping quiz', exc_info=e)
            current_quiz_hl.pop((server_id, user_id), None)
        await safe_response(itc, 'Quiz stopped', ephemeral=True)
