"""Music commands for the bot"""
from functools import wraps

import discord

from discord import app_commands
from discord.ext import commands

from ...import models as m

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

class Music(commands.Cog):
    """Play command"""
    @app_commands.command()
    @sense_check
    async def play(self, itc: discord.Interaction, search: str):
        """Search and Play a song"""
        user = itc.user
        response = itc.response
        guild = user.voice.channel.guild

        await response.send_message(f'Searching for {search}', ephemeral=True)
        song = await m.YTSong.from_search_string(search, user=user, server=guild)

        vc = await get_vc_from_interaction(itc)

        await itc.edit_original_response(content=f'Playing [{song.duration} s] {song.title}')
        await song.play(vc, user=user, server=guild)

    @app_commands.command()
    @sense_check
    async def queue(self, itc: discord.Interaction):
        """Sync the bot commands"""
        guild = itc.guild
        server = await m.DiscordServer.from_discord_guild(guild)
        queue = server.queue
        if not queue:
            await itc.response.send_message(
                "the bot isn't playing anything",
                ephemeral=True,
                delete_after=10
            )
        else:
            res = []
            idx = server.idx
            for i,song in enumerate(queue):
                pre = ' ‣‣‣' if idx == i else f'{i-idx:>4d}'
                res.append(f'{pre} {song.title}')
            queue_str = '\n'.join(res)
            embedVar = discord.Embed(color=0xFF0000)
            embedVar.add_field(name='Now playing:', value=queue_str)
            await itc.response.send_message(embed=embedVar, ephemeral=True)

    @app_commands.command()
    @sense_check
    async def jump(self, itc: discord.Interaction, pos: int = 1):
        """Skip the current song"""
        vc = await get_vc_from_interaction(itc)
        if not vc.is_playing():
            await itc.response.send_message("the bot isn't playing anything")
            return
        if pos < 1:
            await itc.response.send_message('you must skip at least one song')
            return

        guild = itc.guild
        server = await m.DiscordServer.from_discord_guild(guild)
        server.jump_relative(pos)
        vc.stop()
        await itc.response.send_message(f'skipped `{pos}` songs')

    @app_commands.command()
    @sense_check
    async def play_last(self, itc: discord.Interaction):
        """Play the last song"""
        user = itc.user
        guild = itc.guild
        song = await m.YTSong.get_last_played(server=guild)
        vc = await get_vc_from_interaction(itc)
        await itc.response.send_message(f'Playing [{song.duration} s] {song.title}', ephemeral=True)
        await song.play(vc, user=user, server=guild)

    @app_commands.command()
    @sense_check
    async def loop_one(self, itc: discord.Interaction):
        """Loop the last song"""
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        server.queue.loop_all = False
        server.queue.loop_one = True
        await itc.response.send_message('Looping the last song')

    @app_commands.command()
    @sense_check
    async def loop_all(self, itc: discord.Interaction):
        """Loop all songs"""
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        server.queue.loop_all = True
        server.queue.loop_one = False
        await itc.response.send_message('Looping all songs')

    @app_commands.command()
    @sense_check
    async def loop_stop(self, itc: discord.Interaction):
        """Stop looping"""
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        server.queue.loop_all = False
        server.queue.loop_one = False
        await itc.response.send_message('Stopped looping')

    @app_commands.command()
    @sense_check
    async def stop(self, itc: discord.Interaction):
        """Stop the bot"""
        vc = await get_vc_from_interaction(itc)
        await vc.disconnect()
        await itc.response.send_message('Stopped the bot')

    # @app_commands.command()
    # @sense_check
    # async def resume(self, itc: discord.Interaction):
    #     """Resume the bot"""
    #     raise NotImplementedError
    #     vc = itc.guild.voice_client
    #     vc.resume()
    #     await itc.response.send_message('Resumed the bot')
