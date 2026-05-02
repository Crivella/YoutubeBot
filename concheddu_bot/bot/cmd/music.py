"""Music commands for the bot"""
import logging

import discord
from discord import app_commands
from discord.ext import commands

from ... import models as m
from .. import views as v
from ...youtube import YTDLSource
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
            pos: int = 1,
            audio_filter: str = None,
            manual_title: app_commands.Transform[str, tfs.StringLimitedTransformer(max_length=255)] = None,
        ):
        """Play a song from a search string, if a playlist is provided, it will be added to the playlist

        Args:
            song (str): Existing song / search string / youtube url
            playlist (str, optional): Playlist name (must exist). Defaults to None.
            pos (int, optional): Position to add the song in the queue. Defaults to 1 (next song).
            audio_filter (str, optional): FFMPEG audio filter to apply. Defaults to None.
            manual_title (str, optional): Manual title to set for the song. Defaults to None.
        """
        await song.set_manual_title(manual_title, itc=itc)
        await song.add_to_server_from_interaction(itc)
        if playlist is not None:
            await playlist.add_song(song)
        audio_filter = sanitize_ffmpeg_filter(audio_filter)
        await song.play(itc=itc, audio_filter=audio_filter, pos=pos)

    @app_commands.command()
    @ensure_response(allowed_exceptions=[m.YTSong.MaxDurationError])
    @call_command_register()
    async def search_and_add(
            self, itc: discord.Interaction,
            search: str,
            max_results: app_commands.Transform[int, tfs.IntRangeTransformer(min=1, max=20)] = 5,
            playlist: app_commands.Transform[m.Playlist, tfs.PlaylistTransformer] = None,
            play: bool = False,
            manual_title: app_commands.Transform[str, tfs.StringLimitedTransformer(max_length=255)] = None,
        ):
        """Search for a song and add it to the database, if a playlist is provided, it will be added to the playlist

        Args:
            search (str): The search string or youtube url
            max_results (int, optional): The maximum number of search results to return. Defaults to 5.
            playlist (str, optional): Playlist name (must exist). Defaults to None.
            play (bool, optional): Whether to play the song after adding it. Defaults to False.
            manual_title (str, optional): Manual title to set for the song. Defaults to None.
        """
        await safe_response(itc, f'Searching for {search}', ephemeral=True, delete_after=240)

        song = await m.YTSong.from_url(search)
        if song is None:
            songs = await YTDLSource.youtube_search(search, max_results=max_results)
            view = v.SongSearchList(
                itc, songs,
                manual_title=manual_title,
                play=play,
                playlist=playlist
            )
            await safe_response(itc, 'Select a song to add', view=view, ephemeral=True)
            await view.list.go_to_page(0)
        else:
            await song.set_manual_title(manual_title, itc=itc)
            await song.add_to_server_from_interaction(itc)

            msg = f'Added song `{song.title}`'
            if playlist is not None:
                await playlist.add_song(song)
                msg += f' with playlist `{playlist.name}`'
            await safe_response(itc, msg, ephemeral=True, delete_after=30)
            if play:
                await song.play(itc=itc)

    @app_commands.command()
    @call_command_register()
    async def set_manual_title(
            self, itc: discord.Interaction,
            song: app_commands.Transform[m.YTSong, tfs.SongTransformer(allow_new=False)],
            manual_title: app_commands.Transform[str, tfs.StringLimitedTransformer(max_length=255)] = None,
        ):
        """Search for a song and add it to the database and set a manual title

        Args:
            search (str): The search string or youtube url
        """
        old_manual_title = await song.set_manual_title(manual_title, itc=itc)

        await safe_response(
            itc, f'Setting manual title for {song.title} from `{old_manual_title}` to {manual_title}',
            ephemeral=True, delete_after=10
        )


    @app_commands.command()
    @ensure_response(allowed_exceptions=[SenseCheckError])
    @call_command_register()
    @sense_check
    async def play_random(
            self, itc: discord.Interaction,
            num: app_commands.Transform[int, tfs.IntRangeTransformer(min=1, max=50)] = 1
        ):
        """Play from 1 to 10 random songs

        Args:
            num (int, optional): The number of random songs to play. Defaults to 1.
        """
        guild = itc.guild
        server = await m.DiscordServer.from_discord_guild(guild)
        song = await m.YTSong.get_all_songs(server=guild, n=num, sorting='random')
        res = []
        awaitables = []
        duration = 0
        for s in song:
            awaitables.append(s.play(itc=itc, bulk_mode=True))
            duration += s.duration
            res.append(f'[{s.duration} s] {s.title}')
        res += ['-'*30]
        await safe_response(itc, '\n'.join(res), ephemeral=True)
        for a in awaitables:
            await a
        await server.player.print_message()

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
        embed, file = await server.player.generate_embed()
        await safe_response(itc, embed=embed, file=file, ephemeral=True)

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
    @ensure_response()
    @call_command_register()
    async def remove(self, itc: discord.Interaction, pos: int = 0):
        """Remove a song from the queue at the relative index

        Args:
            pos (int, optional): The relative index to remove. Defaults to 0 (the current song).
        """
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        await server.player.remove_source(pos=pos, channel=itc.user.voice.channel)
        await safe_response(itc, f'Removed song at relative index `{pos}`', ephemeral=True, delete_after=10)

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
