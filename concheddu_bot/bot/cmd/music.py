"""Music commands for the bot"""
import asyncio
import logging

import discord

from discord import app_commands
from discord.ext import commands

from ...import models as m
from ..utils import sense_check, safe_response, ensure_response


logger = logging.getLogger('bot')

class Music(commands.Cog):
    """Play command"""
    @app_commands.command()
    @sense_check
    @ensure_response()
    async def play(self, itc: discord.Interaction, search: str, playlist: str = None):
        """Play a song from a search string, if a playlist is provided, it will be added to the playlist

        Args:
            search (str): The search string or youtube url
            playlist (str, optional): Playlist name (must exist). Defaults to None.
        """
        logger.info(f'Command `play` called with search={search} by `{itc.user.name}` [{itc.guild.name}]')
        user = itc.user
        guild = user.voice.channel.guild

        await safe_response(itc, f'Searching for {search}', ephemeral=True, delete_after=240)
        try:
            song = await m.YTSong.from_search_string(search, user=user, server=guild)
        except ValueError as e:
            await safe_response(itc, str(e), ephemeral=True, delete_after=10)
            return
        if playlist is not None:
            server = await m.DiscordServer.from_discord_guild(guild)
            try:
                playlist = await m.Playlist.objects.aget(server=server, name=playlist)
            except m.Playlist.DoesNotExist:
                await itc.response.send_message(
                    f'Playlist `{playlist}` not found',
                    ephemeral=True,
                    delete_after=10
                )
                return
            await playlist.add_song(song)
            await asyncio.sleep(1.0)
        await song.play(itc=itc)
    @play.autocomplete('playlist')
    async def _load_playlist_name(self, itc: discord.Interaction, current: str):
        """Autocomplete the playlist name"""
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        user = await m.DiscordUser.from_discord_user(itc.user)
        playlists = [p async for p in m.Playlist.objects.filter(server=server, owner=user, name__startswith=current)]
        return [app_commands.Choice(name=p.name, value=p.name) for p in playlists]

    @app_commands.command()
    @sense_check
    @ensure_response()
    async def play_random(self, itc: discord.Interaction, num: int = 1):
        """Play from 1 to 10 random songs

        Args:
            num (int, optional): The number of random songs to play. Defaults to 1.
        """
        logger.info(f'Command `play_random` called with num={num} by `{itc.user.name}` [{itc.guild.name}]')
        if num < 1 or num > 10:
            await itc.response.send_message('Number of songs must be between 1 and 10', ephemeral=True, delete_after=10)
            return
        guild = itc.guild
        song = await m.YTSong.get_all_songs(server=guild, n=num, sorting='random')
        res = []
        awaitables = []
        duration = 0
        for s in song:
            awaitables.append(s.play(itc=itc))
            duration += s.duration
            res.append(f'[{s.duration} s] {s.title}')
        res += ['-'*30]
        await safe_response(itc, '\n'.join(res), ephemeral=True)
        for a in awaitables:
            await a

    @app_commands.command()
    @ensure_response()
    async def queue(self, itc: discord.Interaction):
        """Sync the bot commands"""
        logger.info(f'Command `queue` called by `{itc.user.name}` [{itc.guild.name}]')
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        embedVar = discord.Embed(color=0xFF0000)
        embedVar.add_field(name='Now playing:', value=str(server.player.queue))
        await safe_response(itc, embed=embedVar, ephemeral=True)

    @app_commands.command()
    @sense_check
    @ensure_response()
    async def jump(self, itc: discord.Interaction, pos: int = 1):
        """Skip the current song"""
        logger.info(f'Command `jump` called with pos={pos} by `{itc.user.name}` [{itc.guild.name}]')
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        await server.jump(pos, channel=itc.user.voice.channel)
        await safe_response(itc, f'skipped `{pos}` songs', ephemeral=True, delete_after=10)

    @app_commands.command()
    @sense_check
    @ensure_response()
    async def play_last(self, itc: discord.Interaction):
        """Play the last song"""
        logger.info(f'Command `play_last` called by `{itc.user.name}` [{itc.guild.name}]')
        song = await m.YTSong.get_last_played(server=itc.guild)
        await song.play(itc=itc)

    @app_commands.command()
    @sense_check
    @ensure_response()
    async def loop_one(self, itc: discord.Interaction):
        """Loop the last song"""
        logger.info(f'Command `loop_one` called by `{itc.user.name}` [{itc.guild.name}]')
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        server.player.queue.loop_all = False
        server.player.queue.loop_one = True
        await safe_response(itc, 'Looping the last song')

    @app_commands.command()
    @sense_check
    @ensure_response()
    async def loop_all(self, itc: discord.Interaction):
        """Loop all songs"""
        logger.info(f'Command `loop_all` called by `{itc.user.name}` [{itc.guild.name}]')
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        server.player.queue.loop_all = True
        server.player.queue.loop_one = False
        await safe_response(itc, 'Looping all songs')

    @app_commands.command()
    @sense_check
    @ensure_response()
    async def loop_stop(self, itc: discord.Interaction):
        """Stop looping"""
        logger.info(f'Command `loop_stop` called by `{itc.user.name}` [{itc.guild.name}]')
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        server.player.queue.loop_all = False
        server.player.queue.loop_one = False
        await safe_response(itc, 'Stopped looping')

    @app_commands.command()
    @ensure_response()
    async def stop(self, itc: discord.Interaction):
        """Stop the bot"""
        logger.info(f'Command `stop` called by `{itc.user.name}` [{itc.guild.name}]')
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        await server.stop()
        await safe_response(itc, 'Stopped the bot')

    @app_commands.command()
    @sense_check
    @ensure_response()
    async def resume(self, itc: discord.Interaction):
        """Resume the bot"""
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        await server.resume(itc.user.voice.channel)
        await safe_response(itc, 'Resumed the bot')

    @app_commands.command()
    @ensure_response()
    async def clear(self, itc: discord.Interaction):
        """Resume the bot"""
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        await server.clear()
        await safe_response(itc, 'Cleared the bot')
