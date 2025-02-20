import os
import asyncio

import discord

from discord import app_commands
from discord.ext import commands

from . import MyBot
from ..import models as m

async def get_vc_from_interaction(itc: discord.Interaction) -> discord.VoiceClient:
    """Get the voice channel from the interaction"""
    user = itc.user
    guild = itc.guild

    try:
        vc = await user.voice.channel.connect()
    except discord.errors.ClientException:
        vc = guild.voice_client
    return vc

class Music(commands.Cog):
    """Play command"""
    def __init__(self, bot: MyBot):
        self.bot = bot

    @app_commands.command()
    async def play(self, itc: discord.Interaction, search: str):
        """Search and Play a song"""
        if not await self.sense_check(itc):
            return

        user = itc.user
        response = itc.response
        guild = user.voice.channel.guild

        await response.send_message(f'Searching for {search}', ephemeral=True)
        song = await m.YTSong.from_search_string(search, user=user, server=guild)

        vc = await get_vc_from_interaction(itc)

        await itc.edit_original_response(content=f'Playing [{song.duration} s] {song.title}')
        await song.play(vc, user=user, server=guild)

    @app_commands.command()
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
        await self.sense_check(itc)

    @app_commands.command()
    async def jump(self, itc: discord.Interaction, pos: int = 1):
        """Skip the current song"""
        if not await self.sense_check(itc):
            return

        guild = itc.guild
        server = await m.DiscordServer.from_discord_guild(guild)
        vc = guild.voice_client
        if not vc.is_playing():
            await itc.response.send_message("the bot isn't playing anything")
            return
        if pos < 1:
            await itc.response.send_message('you must skip at least one song')
            return
        server.jump(pos)
        vc.stop()
        await itc.response.send_message(f'skipped `{pos}` songs')

    @app_commands.command()
    async def play_last(self, itc: discord.Interaction):
        """Play the last song"""
        if not await self.sense_check(itc):
            return
        user = itc.user
        guild = itc.guild
        song = await m.YTSong.get_last_played(server=guild)
        vc = await get_vc_from_interaction(itc)
        await itc.response.send_message(f'Playing [{song.duration} s] {song.title}', ephemeral=True)
        await song.play(vc, user=user, server=guild)

    # @app_commands.command()
    # async def sync(self, itc: discord.Interaction):
    #     """Sync the bot commands"""
    #     fmt = await self.bot.tree.sync()
    #     print(f'Synced {fmt} commands')
    #     await itc.response.send_message(f'Synced {fmt} commands')

    async def sense_check(self, itc: discord.Interaction) -> bool:
        """Check if the user is in a voice channel"""
        user = itc.user
        guild = itc.guild
        if not user.voice:
            await itc.response.send_message(
                'You must be in a voice channel to use this command',
                ephemeral=True
            )
            return False
        if guild.id in self.bot.playing_on:
            if self.bot.id not in [mb.id for mb in user.voice.channel.members]:
                await itc.response.send_message(
                    'I must be in the same voice channel as you to use this command',
                    ephemeral=True
                )
                return False
        return True

    def after_track(self, error, connection, server_id):
        if error is not None:
            print(error)
        try:
            last_video_path = self.bot.queues[server_id]['queue'][0][0]
            if not self.bot.queues[server_id]['loop']:
                # os.remove(last_video_path)
                self.bot.queues[server_id]['queue'].pop(0)
        except KeyError:
            return  # probably got disconnected
        # if last_video_path not in [i[0] for i in self.bot.queues[server_id]['queue']]: # check that the same video isn't queued multiple times
        #     try:
        #         os.remove(last_video_path)
        #     except FileNotFoundError:
        #         pass
        try:
            nxt = self.bot.queues[server_id]['queue'][0][0]
        except IndexError:  # that was the last item in queue
            self.bot.queues.pop(server_id)  # directory will be deleted on disconnect
            asyncio.run_coroutine_threadsafe(safe_disconnect(connection), self.bot.loop).result()
        else:
            connection.play(
                discord.FFmpegOpusAudio(nxt),
                after=lambda error=None, connection=connection, server_id=server_id: self.after_track(
                    error, connection, server_id
                ),
            )

async def safe_disconnect(connection):
    if not connection.is_playing():
        await connection.disconnect()
