import logging
import sys

import discord
from discord.ext import commands

from .. import models as m

logger = logging.getLogger('bot')

class MyBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.playing_on: set[int] = set()
        self.queues: dict[int, list[str]] = {}

    async def on_ready(self):
        """Make sure the bot is ready before doing anything"""
        logger.info(f'Logged in as {self.user.name} ID<{self.user.id}>')
        fmt = await self.tree.sync()
        for cmd in fmt:
            logging.debug(f'Synced {cmd} commands')

    async def on_error(self, event, *args, **kwargs):
        logger.error(f'Error in {event}')
        tpl = sys.exc_info()
        logger.error(tpl)

    async def on_voice_state_update(
        self, member: discord.User, before: discord.VoiceState, after: discord.VoiceState
    ):
        print(member, before, after, self.user)
        if member != self.user:
            return
        if before.channel is None and after.channel is not None:  # joined vc
            return
        if before.channel is not None and after.channel is None:  # disconnected from vc
            # clean up
            logger.info(f'Leaving {before.channel.name} on [{before.channel.guild.name}]')
            server = await m.DiscordServer.from_discord_guild(before.channel.guild)
            await server.stop()
