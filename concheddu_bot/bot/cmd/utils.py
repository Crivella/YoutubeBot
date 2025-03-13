"""Music commands for the bot"""
import logging
import re
from functools import wraps

import discord
from django.db import models

from ... import models as m

logger = logging.getLogger('bot')

# TODO: need to add proper invalidation before using this
#  probably based on django signals on when playlists are updated
# server_playlist_cache = {}

def sanitize_ffmpeg_filter(afilt: str):
    """Sanitize the ffmpeg filter"""
    if afilt is None:
        return
    rgx = re.compile(r'^[a-z0-9=_:,\-\.]+$')
    res = afilt
    res = res.replace(';', '')
    res = res.replace('|', '')
    res = res.replace('"', '')
    res = res.replace("'", '')

    if not rgx.match(res):
        logger.warning(f'Invalid ffmpeg filter: {afilt}')
        raise ValueError(f'Invalid ffmpeg filter: {afilt}')
    logger.debug(f'Sanitized ffmpeg filter: {afilt} -> {res}')

    return res

def serialize(app):
    """Serialize a model"""
    if isinstance(app, models.Model):
        return f'{app.__class__.__name__}<{app.pk}>'
    elif isinstance(app, (discord.User, discord.Member)):
        return f'{app.__class__.__name__}<{app.id}>'
    return app

def recursive_serialize(obj):
    """Recursively serialize an object"""
    if isinstance(obj, dict):
        return {key: recursive_serialize(obj[key]) for key in obj}
    if isinstance(obj, list):
        return [recursive_serialize(app) for app in obj]
    return serialize(obj)

def call_command_register():
    """Decorator to register a call command event"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if isinstance(args[0], discord.Interaction):
                itc = args[0]
                other_args = args[1:]
            elif isinstance(args[1], discord.Interaction):
                itc = args[1]
                other_args = args[2:]
            else:
                raise ValueError('No interaction found')

            # Ensure all models are converted to strings to be JSON serializable
            other_args = recursive_serialize(other_args)
            other_kwargs = recursive_serialize(kwargs)

            user = await m.DiscordUser.from_discord_user(itc.user)
            server = await m.DiscordServer.from_discord_guild(itc.guild)
            name = itc.command.name
            ptr = itc.command.parent
            while ptr is not None:
                name = f'{ptr.name}:{name}'
                ptr = ptr.parent

            logger.debug(f'Command `{name}` called by `{itc.user.name}` on [{itc.guild.name}]')
            event = await m.CallCommandEvent.objects.acreate(
                user=user,
                server=server,
                command=name,
                args=other_args,
                kwargs=other_kwargs,
            )
            try:
                res = await func(*args, **kwargs)
            except Exception as e:
                event.error = str(e)
                await event.asave()
                raise e
            return res
        return wrapper
    return decorator
