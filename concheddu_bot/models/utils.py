import logging
import re
from functools import wraps

import discord
from django.apps import apps

logger = logging.getLogger('bot')

def title_cleaner(title: str) -> str:
    """Clean the title"""
    res = title
    res = re.sub(r'「[^」]*」?', '', res)
    res = re.sub(r'『[^』]*』?', '', res)
    res = re.sub(r'\[[^\]]*\] ?', '', res)
    res = re.sub(r'creditless', '', res, flags=re.I)
    res = re.sub(r'4K ?', '', res, flags=re.I)
    res = re.sub(r'1080p ?', '', res, flags=re.I)
    res = re.sub(r'U?HD ?', '', res, flags=re.I)
    res = re.sub(r'\d* ?FPS ?', '', res, flags=re.I)
    return res


def extract_server_user_from_itc_async(func):
    """Decorator to extract server and user from interaction"""
    @wraps(func)
    async def wrapper(self, *args, itc: discord.Interaction, **kwargs):
        server_cls = apps.get_model('concheddu_bot', 'DiscordServer')
        user_cls = apps.get_model('concheddu_bot', 'DiscordUser')

        server = await server_cls.from_discord_guild(itc.guild)
        user = await user_cls.from_discord_user(itc.user)
        user.dc = itc.user
        return await func(self, itc=itc, server=server, user=user, *args, **kwargs)

    return wrapper

def with_discord_user_async(func):
    """Decorator to add discord user to kwargs"""
    @wraps(func)
    async def wrapper(*args, user, **kwargs):
        user_cls = apps.get_model('concheddu_bot', 'DiscordUser')
        if isinstance(user, (discord.User, discord.Member)):
            user_obj = await user_cls.from_discord_user(user)
            user_obj.dc = user
        elif isinstance(user, user_cls):
            user_obj = user
        else:
            raise ValueError(f'Invalid user type {type(user)}')
        return await func(*args, user=user_obj, **kwargs)
    return wrapper

def with_discord_server_async(func):
    """Decorator to add discord server to kwargs"""
    @wraps(func)
    async def wrapper(*args, server, **kwargs):
        server_cls = apps.get_model('concheddu_bot', 'DiscordServer')
        if isinstance(server, discord.Guild):
            server_obj = await server_cls.from_discord_guild(server)
            server_obj.dc = server
        elif isinstance(server, server_cls):
            server_obj = server
        else:
            raise ValueError('Invalid server type')
        return await func(*args, server=server_obj, **kwargs)
    return wrapper
