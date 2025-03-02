"""Utility functions for the bot"""
from functools import wraps

import discord

from .. import models as m


async def get_vc_from_user(user: discord.Member) -> discord.VoiceClient:
    """Get the voice channel from the user"""
    if not user:
        return
    guild = user.guild
    if (vc := guild.voice_client):
        return vc
    if not user.voice:
        return
    try:
        vc = await user.voice.channel.connect()
    except discord.errors.ClientException:
        return
    return vc

async def get_vc_from_interaction(itc: discord.Interaction) -> discord.VoiceClient:
    """Get the voice channel from the interaction"""
    user = itc.user
    guild = itc.guild

    try:
        vc = await user.voice.channel.connect()
    except discord.errors.ClientException:
        vc = guild.voice_client
    return vc

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
