import os
import asyncio

import discord

from discord import app_commands
from discord.ext import commands

from . import MyBot
from ..import youtube as yt
# from ..import models as m

class Music(commands.Cog):
    """Play command"""
    def __init__(self, bot: MyBot):
        self.bot = bot

    @app_commands.command()
    # @commands.command()
    async def play_test(self, itc: discord.Interaction, search: str):
        """Search and Play a song"""
        from ..import models as m
        if not await self.sense_check(itc):
            return

        user_dc = itc.user
        response = itc.response
        guild = user_dc.voice.channel.guild

        await response.send_message(f'Searching for {search}', ephemeral=True)
        source = await yt.YTDLSource.from_url(search, loop=self.bot.loop)
        data = source.data
        ytid = source.data['id']
        ext = source.data['ext']
        song, created = await m.YTSong.objects.aget_or_create(youtube_id=ytid)
        if created:
            for attr in ['title', 'duration']:
                setattr(song, attr, source.data[attr])
        path = os.path.join(yt.AUDIO_DIR, f'{ytid}.{ext}')
        if os.path.exists(path):
            song.extension = ext
            song.local_path = path
            source = discord.FFmpegPCMAudio(path)
        await song.asave()

        # message = itc.original_response()
        await itc.edit_original_response(content=f'Playing [{song.duration} s] {song.title}')
        await song.play(user=user_dc)

        try:
            vc = await user_dc.voice.channel.connect()
        except discord.errors.ClientException:
            vc = guild.voice_client
        self.bot.queues.setdefault(guild.id, {'queue': [], 'loop': False})
        self.bot.queues[guild.id]['queue'].append((path, data))
        if not vc.is_playing():
            vc.play(
                source,
                after=lambda error=None, connection=vc, server_id=guild.id: self.after_track(
                    error, connection, server_id
                ),
            )

    @app_commands.command()
    async def queue(self, itc: discord.Interaction):
        """Sync the bot commands"""
        guild = itc.guild
        try:
            queue = self.bot.queues[guild.id]['queue']
        except KeyError:
            queue = None
        if queue == None:
            await itc.response.send_message("the bot isn't playing anything")
        else:
            title_str = lambda val: (
                f'‣ {val[1]}\n\n' if val[0] == 0 else '**%2d:** %s\n' % val
            )
            queue_str = ''.join(map(title_str, enumerate([i[1]['title'] for i in queue])))
            embedVar = discord.Embed(color=0xFF0000)
            embedVar.add_field(name='Now playing:', value=queue_str)
            await itc.response.send_message(embed=embedVar)
        await self.sense_check(itc)

    # @app_commands.command()
    # async def sync(self, itc: discord.Interaction):
    #     """Sync the bot commands"""
    #     fmt = await self.bot.tree.sync()
    #     print(f'Synced {fmt} commands')
    #     await itc.response.send_message(f'Synced {fmt} commands')

    # @commands.command()
    # async def sync_test(self, ctx: commands.Context):
    #     """Sync the bot commands"""
    #     guild_id = ctx.guild.id
    #     await ctx.send(f'Syncing commands for {guild_id}')
    #     fmt = await self.bot.tree.sync(guild_id)
    #     print(f'Synced {fmt} commands')
    #     await ctx.send(f'Synced {fmt} commands')

    async def sense_check(self, itc: discord.Interaction) -> bool:
        """Check if the user is in a voice channel"""
        user_dc = itc.user
        guild = itc.guild
        if not user_dc.voice:
            await itc.response.send_message(
                'You must be in a voice channel to use this command',
                ephemeral=True
            )
            return False
        if guild.id in self.bot.playing_on:
            if self.bot.id not in [mb.id for mb in user_dc.voice.channel.members]:
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
