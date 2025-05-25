import logging
import sys

import discord
from discord import app_commands
from discord.ext import commands

from .. import models as m
from .utils import DEBUG_MESSAGES, safe_response

logger = logging.getLogger('bot')

current_bot: discord.Client | None = None

def get_current_bot() -> discord.Client | None:
    """Get the current bot instance"""
    global current_bot
    return current_bot

class MyBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.playing_on: set[int] = set()
        self.queues: dict[int, list[str]] = {}

        global current_bot
        current_bot = self

        self.tree.error(self._on_tree_error)

    async def on_ready(self):
        """Make sure the bot is ready before doing anything"""
        logger.info(f'Logged in as {self.user.name} ID<{self.user.id}>')
        fmt = await self.tree.sync()
        for cmd in fmt:
            logging.debug(f'Synced {cmd} commands')

    async def _on_tree_error(self, ctx: discord.Interaction, error: app_commands.AppCommandError):
        """Handle errors from the command tree"""
        name = ctx.command.name
        ptr = ctx.command.parent
        while ptr is not None:
            name = f'{ptr.name}:{name}'
            ptr = ptr.parent
        logger.error(f'Error in `{name}` command {error}', exc_info=True)
        if DEBUG_MESSAGES:
            await safe_response(ctx, f'Error in `{name}` command {error}', ephemeral=True)
        else:
            await safe_response(ctx, f'Error in `{name}`', ephemeral=True)

    async def on_error(self, event, *args, **kwargs):
        logger.error(f'Error in {event}')
        tpl = sys.exc_info()
        logger.error(tpl)

    async def on_voice_state_update(
        self, member: discord.User, before: discord.VoiceState, after: discord.VoiceState
    ):
        if member != self.user:
            return
        if before.channel is None and after.channel is not None:  # joined vc
            return
        if before.channel is not None and after.channel is None:  # disconnected from vc
            # clean up
            logger.info(f'Leaving {before.channel.name} on [{before.channel.guild.name}]')
            server = await m.DiscordServer.from_discord_guild(before.channel.guild)
            server.player.client = None
            server.player.channel = None
            await server.stop()
