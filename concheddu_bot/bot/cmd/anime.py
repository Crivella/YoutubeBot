"""Anime commands for the bot"""
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

class Anime(commands.GroupCog, group_name='anime'):
    """Anime command"""
    def __init__(self, *args, bot, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot

    @app_commands.command()
    @ensure_response()
    @call_command_register()
    async def show(
            self, itc: discord.Interaction,
            anime: app_commands.Transform[m.AnimeObj, tfs.AnimeTransformer]
        ):
        """Show details of an anime

        Args:
            itc (discord.Interaction): The interaction context
            anime (m.AnimeObj): The anime object to show
        """
        embed, file = await anime.to_embed()
        await safe_response(itc, embed=embed, file=file)

    @app_commands.command()
    @ensure_response()
    @call_command_register()
    async def show_characters(
            self, itc: discord.Interaction,
            anime: app_commands.Transform[m.AnimeObj, tfs.AnimeTransformer],
            num: app_commands.Transform[int, tfs.IntRangeTransformer(min=1, max=10)] = 5
        ):
        """Show top `num` characters of an anime
        Args:
            itc (discord.Interaction): The interaction context
            anime (m.AnimeObj): The anime object to show characters for
            num (int): The number of characters to show (default: 10)
        """
        characters = await anime.get_characters(top=num)
        embeds = []
        files = []
        for character in characters:
            embed, file = await character.to_embed()
            embeds.append(embed)
            files.append(file)
        await safe_response(itc, embeds=embeds, files=files)

    @app_commands.command()
    @ensure_response(before=True, defer=True)
    @call_command_register()
    async def import_id(self, itc: discord.Interaction, anime_id: int):
        """Import an anime from MyAnimeList by ID

        Args:
            itc (discord.Interaction): The interaction context
            anime_id (int): The ID of the anime to import from MyAnimeList
        """
        obj = await m.AnimeObj.from_id(anime_id)
        if obj is None:
            await safe_response(itc, f'Anime with id {anime_id} not found', ephemeral=True)
        else:
            await safe_response(itc, f'Found anime: {obj.title} ({obj.id})', ephemeral=True)

    @app_commands.command()
    @app_commands.check(lambda itc: itc.user.id == ADMIN_ID)
    @ensure_response(before=True, defer=True)
    @call_command_register()
    async def import_top(
        self, itc: discord.Interaction,
        start: int,
        num: int
        ):
        """Import the top `num` anime from MyAnimeList

        Args:
            itc (discord.Interaction): The interaction context
            start (int): The starting index of the top anime to import
            num (int): The number of top anime to import
        """
        res = await m.AnimeObj.from_top(start, num)
        logger.info(f'Found {len(res)} anime in top {num}')
        await safe_response(itc, f'Imported {len(res)} anime', ephemeral=True)



    # @app_commands.command()
    # @ensure_response()
    # @call_command_register()
    # async def search(self, itc: discord.Interaction, query: str):
    #     """Search for an anime"""
    #     await safe_response(itc, f'Searching for anime: {query}', ephemeral=True)
    #     results = await m.Anime.objects.asearch(query)
    #     if not results:
    #         return await safe_response(itc, 'No results found', ephemeral=True)

    #     embed = discord.Embed(title='Anime Search Results', color=discord.Color.blurple())
    #     for anime in results:
    #         embed.add_field(name=anime.title, value=f'ID: {anime.id}', inline=False)

    #     await itc.response.send_message(embed=embed)
