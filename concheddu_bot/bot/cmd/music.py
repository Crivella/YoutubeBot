"""Music commands for the bot"""
import logging

import discord

from discord import app_commands
from discord.ext import commands

from ...import models as m
from ..utils import sense_check


logger = logging.getLogger('bot')

class Music(commands.Cog):
    """Play command"""
    @app_commands.command()
    @sense_check
    async def play(self, itc: discord.Interaction, search: str):
        """Search and Play a song"""
        logger.info(f'Command `play` called with search={search} by `{itc.user.name}` [{itc.guild.name}]')
        user = itc.user
        response = itc.response
        guild = user.voice.channel.guild

        await response.send_message(f'Searching for {search}', ephemeral=True)
        try:
            song = await m.YTSong.from_search_string(search, user=user, server=guild)
        except Exception as e:
            await itc.edit_original_response(content=f'Error: {e}')
            return

        if song.need_download:
            await itc.edit_original_response(content=f'Downloading `{song.title}`')
            await song.download()
        await itc.edit_original_response(content=f'Playing [{song.duration} s] {song.title}')
        await song.play(user=user, server=guild)

    @app_commands.command()
    @sense_check
    async def play_random(self, itc: discord.Interaction, num: int = 1):
        """Play from 1 to 10 random songs

        Args:
            num (int, optional): The number of random songs to play. Defaults to 1.
        """
        logger.info(f'Command `play_random` called with num={num} by `{itc.user.name}` [{itc.guild.name}]')
        if num < 1 or num > 10:
            await itc.response.send_message('Number of songs must be between 1 and 10', ephemeral=True, delete_after=10)
            return
        user = itc.user
        guild = itc.guild
        song = await m.YTSong.get_all_songs(server=guild, n=num, sorting='random')
        res = []
        awaitables = []
        duration = 0
        for s in song:
            awaitables.append(s.play(user=user, server=guild))
            duration += s.duration
            res.append(f'[{s.duration} s] {s.title}')
        await itc.response.send_message('\n'.join(res), ephemeral=True, delete_after=duration)
        for a in awaitables:
            await a

    @app_commands.command()
    async def queue(self, itc: discord.Interaction):
        """Sync the bot commands"""
        logger.info(f'Command `queue` called by `{itc.user.name}` [{itc.guild.name}]')
        pre = 4
        post = 7
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
            idx = server.queue.idx
            if idx > pre:
                res.append('`...`')
            for i in range(max(0, idx-pre), min(len(queue), idx+post)):
                pre = '`` ‣‣‣`' if idx == i else f'`{i-idx:>4d}`'
                res.append(f'{pre} {queue[i].title}')
            if idx + post < len(queue):
                res.append('`...`')
            queue_str = '\n'.join(res)
            embedVar = discord.Embed(color=0xFF0000)
            embedVar.add_field(name='Now playing:', value=queue_str)
            await itc.response.send_message(embed=embedVar, ephemeral=True)

    @app_commands.command()
    @sense_check
    async def jump(self, itc: discord.Interaction, pos: int = 1):
        """Skip the current song"""
        logger.info(f'Command `jump` called with pos={pos} by `{itc.user.name}` [{itc.guild.name}]')
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        server.jump_relative(pos)
        vc = itc.guild.voice_client
        if vc and vc.is_playing():
            vc.stop()
        else:
            user = await m.DiscordUser.from_discord_user(itc.user)
            user.dc = itc.user
            song = server.get_next_song()
            await song._play(user=user, server=server)
        await itc.response.send_message(f'skipped `{pos}` songs')

    @app_commands.command()
    @sense_check
    async def play_last(self, itc: discord.Interaction):
        """Play the last song"""
        logger.info(f'Command `play_last` called by `{itc.user.name}` [{itc.guild.name}]')
        user = itc.user
        guild = itc.guild
        song = await m.YTSong.get_last_played(server=guild)
        await itc.response.send_message(f'Playing [{song.duration} s] {song.title}', ephemeral=True)
        await song.play(user=user, server=guild)

    @app_commands.command()
    @sense_check
    async def loop_one(self, itc: discord.Interaction):
        """Loop the last song"""
        logger.info(f'Command `loop_one` called by `{itc.user.name}` [{itc.guild.name}]')
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        server.queue.loop_all = False
        server.queue.loop_one = True
        await itc.response.send_message('Looping the last song')

    @app_commands.command()
    @sense_check
    async def loop_all(self, itc: discord.Interaction):
        """Loop all songs"""
        logger.info(f'Command `loop_all` called by `{itc.user.name}` [{itc.guild.name}]')
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        server.queue.loop_all = True
        server.queue.loop_one = False
        await itc.response.send_message('Looping all songs')

    @app_commands.command()
    @sense_check
    async def loop_stop(self, itc: discord.Interaction):
        """Stop looping"""
        logger.info(f'Command `loop_stop` called by `{itc.user.name}` [{itc.guild.name}]')
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        server.queue.loop_all = False
        server.queue.loop_one = False
        await itc.response.send_message('Stopped looping')

    @app_commands.command()
    async def stop(self, itc: discord.Interaction):
        """Stop the bot"""
        logger.info(f'Command `stop` called by `{itc.user.name}` [{itc.guild.name}]')
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        server.stop()
        vc = itc.guild.voice_client
        await itc.response.send_message('Stopped the bot', ephemeral=True)
        if vc:
            await vc.disconnect(force=True)

    # @app_commands.command()
    # @sense_check
    # async def resume(self, itc: discord.Interaction):
    #     """Resume the bot"""
    #     raise NotImplementedError
    #     vc = itc.guild.voice_client
    #     vc.resume()
    #     await itc.response.send_message('Resumed the bot')
