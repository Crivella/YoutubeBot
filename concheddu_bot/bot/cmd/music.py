"""Music commands for the bot"""
import logging

import discord
from discord import app_commands
from discord.ext import commands

from ... import models as m
from .. import views as v
from ..utils import (SenseCheckError, ensure_response, safe_response,
                     sense_check)
from . import transformers as tfs
from .utils import call_command_register, sanitize_ffmpeg_filter

logger = logging.getLogger('bot')

class Music(commands.GroupCog, group_name='music'):
    """Play command"""
    @app_commands.command()
    @ensure_response(allowed_exceptions=[m.YTSong.MaxDurationError, SenseCheckError])
    @call_command_register()
    @sense_check
    async def play(
            self, itc: discord.Interaction,
            song: app_commands.Transform[m.YTSong, tfs.SongTransformer(allow_new=True)],
            playlist: app_commands.Transform[m.Playlist, tfs.PlaylistTransformer] = None,
            audio_filter: str = None
        ):
        """Play a song from a search string, if a playlist is provided, it will be added to the playlist

        Args:
            song (str): Existing song / search string / youtube url
            playlist (str, optional): Playlist name (must exist). Defaults to None.
            audio_filter (str, optional): FFMPEG audio filter to apply. Defaults to None.
        """
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        user = await m.DiscordUser.from_discord_user(itc.user)
        await server.add_song(song=song, user=user)
        if playlist is not None:
            await playlist.add_song(song)
        audio_filter = sanitize_ffmpeg_filter(audio_filter)
        await song.play(itc=itc, audio_filter=audio_filter)

    @app_commands.command()
    @ensure_response(allowed_exceptions=[m.YTSong.MaxDurationError])
    @call_command_register()
    async def search_and_add(
            self, itc: discord.Interaction,
            search: str,
            playlist: app_commands.Transform[m.Playlist, tfs.PlaylistTransformer] = None,
        ):
        """Search for a song and add it to the database, if a playlist is provided, it will be added to the playlist

        Args:
            search (str): The search string or youtube url
            playlist (str, optional): Playlist name (must exist). Defaults to None.
        """
        user = itc.user
        guild = itc.guild

        await safe_response(itc, f'Searching for {search}', ephemeral=True, delete_after=240)

        song = await m.YTSong.from_search_string(search)
        if song:
            server = await m.DiscordServer.from_discord_guild(guild)
            user = await m.DiscordUser.from_discord_user(user)
            await server.add_song(song=song, user=user)

        msg = f'Added song `{song.title}`'
        if playlist is not None:
            await playlist.add_song(song)
            msg += f' with playlist `{playlist.name}`'
        await safe_response(itc, msg, ephemeral=True, delete_after=30)

    @app_commands.command()
    @ensure_response(allowed_exceptions=[SenseCheckError])
    @call_command_register()
    @sense_check
    async def play_random(
            self, itc: discord.Interaction,
            num: app_commands.Transform[int, tfs.IntRangeTransformer(min=1, max=10)] = 1
        ):
        """Play from 1 to 10 random songs

        Args:
            num (int, optional): The number of random songs to play. Defaults to 1.
        """
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
    @ensure_response(before=True, defer=True)  # Defer to avoid timeout
    @call_command_register()
    async def list_songs(
            self, itc: discord.Interaction,
            num: app_commands.Transform[int, tfs.IntRangeTransformer(min=1, max=1000)] = 100,
            sorting: app_commands.Transform[str, tfs.SongFilterTransformer] = 'times_played',
            filter_title: str = None,
            ascending: bool = None
        ):
        """Generate a list of songs already known to the bot

        Args:
            num (int, optional): Number of songs to list. Defaults to 100.
            sorting (str, optional): Sorting option. Defaults to 'times_played'.
            filter_title (str, optional): Filter the songs by title. Defaults to None.
            ascending (bool, optional): Sort in ascending order. Defaults to server auto-detect.
        """
        guild = itc.guild
        server = await m.DiscordServer.from_discord_guild(guild)
        songs = await m.YTSong.get_all_songs(
            server=server,
            n=num,
            sorting=sorting,
            filter_title=filter_title,
            asc=ascending
            )
        view = v.SongList(itc, songs)
        await safe_response(
            itc,
            'Select a song to play',
            view=view,
            ephemeral=True
        )
        await view.list.go_to_page(0)

class MusicPlayer(commands.GroupCog, group_name='player'):
    @app_commands.command()
    @ensure_response()
    @call_command_register()
    async def queue(self, itc: discord.Interaction):
        """Show the current queue of songs"""
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        embedVar = discord.Embed(color=0xFF0000)
        loop_str = ''
        if server.player.queue.loop_all:
            loop_str = '(loop all)'
        elif server.player.queue.loop_one:
            loop_str = '(loop one)'
        embedVar.add_field(name=f'Now playing: {loop_str}', value=str(server.player.queue))
        await safe_response(itc, embed=embedVar, ephemeral=True)

    @app_commands.command()
    @ensure_response(allowed_exceptions=[SenseCheckError])
    @call_command_register()
    @sense_check
    async def jump(self, itc: discord.Interaction, pos: int = 1):
        """Skip the current song"""
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        await server.jump(pos, channel=itc.user.voice.channel)
        await safe_response(itc, f'skipped `{pos}` songs', ephemeral=True, delete_after=10)

    @app_commands.command()
    @ensure_response(allowed_exceptions=[SenseCheckError])
    @call_command_register()
    @sense_check
    async def play_last(self, itc: discord.Interaction):
        """Play the last song"""
        song = await m.YTSong.get_last_played(server=itc.guild)
        await song.play(itc=itc)

    @app_commands.command()
    @ensure_response(allowed_exceptions=[SenseCheckError])
    @call_command_register()
    @sense_check
    async def loop_one(self, itc: discord.Interaction):
        """Loop the last song"""
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        server.player.queue.loop_all = False
        server.player.queue.loop_one = True
        await safe_response(itc, 'Looping the last song', ephemeral=True, delete_after=10)

    @app_commands.command()
    @ensure_response(allowed_exceptions=[SenseCheckError])
    @call_command_register()
    @sense_check
    async def loop_all(self, itc: discord.Interaction):
        """Loop all songs"""
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        server.player.queue.loop_all = True
        server.player.queue.loop_one = False
        await safe_response(itc, 'Looping all songs', ephemeral=True, delete_after=10)

    @app_commands.command()
    @ensure_response(allowed_exceptions=[SenseCheckError])
    @call_command_register()
    @sense_check
    async def loop_stop(self, itc: discord.Interaction):
        """Stop looping"""
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        server.player.queue.loop_all = False
        server.player.queue.loop_one = False
        await safe_response(itc, 'Stopped looping', ephemeral=True, delete_after=10)

    @app_commands.command()
    @ensure_response()
    @call_command_register()
    async def stop(self, itc: discord.Interaction):
        """Stop the bot"""
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        await server.stop()
        await safe_response(itc, 'Stopped the bot', ephemeral=True, delete_after=10)

    @app_commands.command()
    @ensure_response(allowed_exceptions=[SenseCheckError])
    @call_command_register()
    @sense_check
    async def pause(self, itc: discord.Interaction):
        """Pause the bot"""
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        await server.pause()
        await safe_response(itc, 'Paused the bot', ephemeral=True, delete_after=10)

    @app_commands.command()
    @ensure_response(allowed_exceptions=[SenseCheckError])
    @call_command_register()
    @sense_check
    async def resume(self, itc: discord.Interaction):
        """Resume the bot"""
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        await server.resume(itc.user.voice.channel)
        await safe_response(itc, 'Resumed the bot', ephemeral=True, delete_after=10)

    @app_commands.command()
    @ensure_response()
    @call_command_register()
    async def clear(self, itc: discord.Interaction):
        """Resume the bot"""
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        await server.clear()
        await safe_response(itc, 'Cleared the bot', ephemeral=True, delete_after=10)
