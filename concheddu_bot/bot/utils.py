"""Utility functions for the bot"""
import logging
import os
from functools import wraps

import discord

from .. import models as m

DEBUG_MESSAGES = os.getenv('BOT_DEBUG_MESSAGES', 'f').lower() in ['true', '1', 't', 'y', 'yes', 'on']

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
        await itc.response.defer(ephemeral=True)
    except discord.errors.InteractionResponded:
        pass
    except discord.errors.NotFound:
        pass

async def safe_response(itc: discord.Interaction, content: str = '', append: bool = False, *args, **kwargs):
    if itc is None:
        return
    msg = []
    if itc.response.is_done():
        rfunc = itc.edit_original_response
        kwargs.pop('ephemeral', None)
        kwargs.pop('delete_after', None)
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

def itc_from_args(args):
    """Get the interaction object from the args.
    Accounts for both wrapping normal functions and class methods"""
    if isinstance(args[0], discord.Interaction):
        return args[0]
    elif isinstance(args[1], discord.Interaction):
        return args[1]
    raise ValueError('No interaction object found')

def ensure_response(before=False, defer=False, allowed_exceptions: list = ()):
    """Decorator to ensure a response is always sent"""
    def wrapper(func):
        """Decorator to catch errors and make sure an interaction is always responded to"""
        @wraps(func)
        async def wrapped(*args, **kwargs):
            itc = itc_from_args(args)

            if before and not itc.response.is_done():
                if defer:
                    await safe_defer(itc)
                else:
                    await safe_response(itc, 'DONE', ephemeral=True, delete_after=10)
            try:
                await func(*args, **kwargs)
            except allowed_exceptions as e:
                logger.debug(f'Allowed exception in {func.__name__}: {e}')
                await safe_response(itc, str(e), ephemeral=True)
            except Exception as e:
                logger.error(f'Error in {func.__name__}: {e}', exc_info=True)
                if DEBUG_MESSAGES:
                    msg = f'Error in {func.__name__}: {e}'
                else:
                    msg = 'An error occurred'
                await safe_response(itc, msg, ephemeral=True)
            else:
                if not before and not itc.response.is_done():
                    if defer:
                        await safe_defer(itc)
                    else:
                        await safe_response(itc, 'DONE', ephemeral=True, delete_after=10)
        return wrapped
    return wrapper

def ensure_user(users: list[discord.Member], defer=False):
    """Decorator to ensure that the user is in the list of users"""
    def wrapper(func):
        @wraps(func)
        async def wrapped(*args, **kwargs):
            itc = itc_from_args(args)
            if itc.user not in users:
                if defer:
                    await safe_defer(itc)
                else:
                    await safe_response(
                        itc, 'You cannot interact with this element',
                        ephemeral=True, delete_after=10
                    )
                return
            return await func(*args, **kwargs)
        return wrapped
    return wrapper
