"""Utility functions for the bot"""
import logging
from functools import wraps

import discord

from .. import models as m

logger = logging.getLogger('bot')

async def safe_disconnect(connection: discord.VoiceClient):
    """Disconnect the bot from the voice channel"""
    if connection is None:
        return
    if connection.is_playing():
        connection.stop()
    await connection.disconnect(force=True)

def sense_check(func):
    """Check if the user can use the command"""
    @wraps(func)
    async def wrapper(self, itc: discord.Interaction, *args, **kwargs):
        user = itc.user
        guild = itc.guild
        if not user.voice:
            await itc.response.send_message(
                'You must be in a voice channel to use this command',
                ephemeral=True
            )
            return
        server = await m.DiscordServer.from_discord_guild(guild)
        if server.playing and user.voice.channel != server.channel:
            await itc.response.send_message(
                'Bot already playing. You must be in the same voice channel as you to use this command',
                ephemeral=True
            )
            return
        return await func(self, itc, *args, **kwargs)
    return wrapper

async def safe_defer(itc: discord.Interaction):
    try:
        await itc.response.defer()
    except discord.errors.NotFound:
        pass

async def safe_response(itc: discord.Interaction, content: str = '', append: bool = False, *args, **kwargs):
    if itc is None:
        return
    msg = []
    if itc.response.is_done():
        rfunc = itc.edit_original_response
        kwargs.pop('ephemeral', None)
        if append:
            resp = await itc.original_response()
            msg.append(resp.content)
    else:
        rfunc = itc.response.send_message
    msg.append(content)

    try:
        await rfunc(content='\n'.join(msg), *args, **kwargs)
    except Exception as e:
        logger.error(f'Error sending message: {e}', exc_info=True)

def ensure_response(before=False, defer=False):
    def wrapper(func):
        """Decorator to catch errors and make sure an interaction is always responded to"""
        @wraps(func)
        async def wrapped(self, itc: discord.Interaction, *args, **kwargs):
            if before and not itc.response.is_done():
                if defer:
                    await safe_defer(itc)
                else:
                    await safe_response(itc, '', ephemeral=True)
            try:
                await func(self, itc, *args, **kwargs)
            except Exception as e:
                logger.error(f'Error in {func.__name__}: {e}', exc_info=True)
                await safe_response(itc, f'Error: {e}', ephemeral=True)
            else:
                if not before and not itc.response.is_done():
                    if defer:
                        await safe_defer(itc)
                    else:
                        await safe_response(itc, '', ephemeral=True, delete_after=10)
        return wrapped
    return wrapper
