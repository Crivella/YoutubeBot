"""Music commands for the bot"""
import logging

import discord

from discord import app_commands
from discord.ext import commands

from ...import models as m
from .utils import sanitize_ffmpeg_filter, PlaylistTransformer, SongFilterTransformer
from ..utils import sense_check, safe_response, ensure_response
from .. import views as v

logger = logging.getLogger('bot')

class Music(commands.GroupCog, group_name='music'):
    """Play command"""
    @app_commands.command()
    @sense_check
    @ensure_response(allowed_exceptions=[m.YTSong.MaxDurationError])
    async def play(
            self, itc: discord.Interaction,
            search: str,
            playlist: app_commands.Transform[m.Playlist, PlaylistTransformer] = None,
            audio_filter: str = None
        ):
        """Play a song from a search string, if a playlist is provided, it will be added to the playlist

        Args:
            search (str): The search string or youtube url
            playlist (str, optional): Playlist name (must exist). Defaults to None.
            audio_filter (str, optional): FFMPEG audio filter to apply. Defaults to None.
        """
        logger.info(f'Command `play` called with search={search} by `{itc.user.name}` [{itc.guild.name}]')
        user = itc.user
        guild = user.voice.channel.guild

        await safe_response(itc, f'Searching for {search}', ephemeral=True, delete_after=240)

        song = await m.YTSong.from_search_string(search, user=user, server=guild)

        if playlist is not None:
            await playlist.add_song(song)
        audio_filter = sanitize_ffmpeg_filter(audio_filter)
        await song.play(itc=itc, audio_filter=audio_filter)

    @app_commands.command()
    @ensure_response(allowed_exceptions=[m.YTSong.MaxDurationError])
    async def search_and_add(
            self, itc: discord.Interaction,
            search: str,
            playlist: app_commands.Transform[m.Playlist, PlaylistTransformer],
        ):
        """Search for a song and add it to the database, if a playlist is provided, it will be added to the playlist

        Args:
            search (str): The search string or youtube url
            playlist (str, optional): Playlist name (must exist). Defaults to None.
        """
        logger.info(f'Command `search_and_add` called with search={search} by `{itc.user.name}` [{itc.guild.name}]')
        user = itc.user
        guild = itc.guild

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

        await safe_response(itc, f'Searching for {search}', ephemeral=True, delete_after=240)

        song = await m.YTSong.from_search_string(search, user=user, server=guild)

        msg = f'Added song `{song.title}`'
        if playlist is not None:
            await playlist.add_song(song)
            msg += f' with playlist `{playlist.name}`'
        await safe_response(itc, msg, ephemeral=True, delete_after=30)

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
    @ensure_response(before=True, defer=True)  # Defer to avoid timeout
    async def list_songs(
            self, itc: discord.Interaction,
            num: int = 100,
            # sorting: str = 'times_played',
            sorting: app_commands.Transform[str, SongFilterTransformer] = 'times_played',
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
        logger.info(f'Command `list_songs` called with num={num}, sorting={sorting} by `{itc.user.name}` [{itc.guild.name}]')
        guild = itc.guild
        server = await m.DiscordServer.from_discord_guild(guild)
        songs = await m.YTSong.get_all_songs(
            server=server, n=num, sorting=sorting,
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
        await safe_response(itc, 'Looping the last song', ephemeral=True, delete_after=10)

    @app_commands.command()
    @sense_check
    @ensure_response()
    async def loop_all(self, itc: discord.Interaction):
        """Loop all songs"""
        logger.info(f'Command `loop_all` called by `{itc.user.name}` [{itc.guild.name}]')
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        server.player.queue.loop_all = True
        server.player.queue.loop_one = False
        await safe_response(itc, 'Looping all songs', ephemeral=True, delete_after=10)

    @app_commands.command()
    @sense_check
    @ensure_response()
    async def loop_stop(self, itc: discord.Interaction):
        """Stop looping"""
        logger.info(f'Command `loop_stop` called by `{itc.user.name}` [{itc.guild.name}]')
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        server.player.queue.loop_all = False
        server.player.queue.loop_one = False
        await safe_response(itc, 'Stopped looping', ephemeral=True, delete_after=10)

    @app_commands.command()
    @ensure_response()
    async def stop(self, itc: discord.Interaction):
        """Stop the bot"""
        logger.info(f'Command `stop` called by `{itc.user.name}` [{itc.guild.name}]')
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        await server.stop()
        await safe_response(itc, 'Stopped the bot', ephemeral=True, delete_after=10)

    @app_commands.command()
    @sense_check
    @ensure_response()
    async def pause(self, itc: discord.Interaction):
        """Pause the bot"""
        logger.info(f'Command `pause` called by `{itc.user.name}` [{itc.guild.name}]')
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        await server.pause()
        await safe_response(itc, 'Paused the bot', ephemeral=True, delete_after=10)

    @app_commands.command()
    @sense_check
    @ensure_response()
    async def resume(self, itc: discord.Interaction):
        """Resume the bot"""
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        await server.resume(itc.user.voice.channel)
        await safe_response(itc, 'Resumed the bot', ephemeral=True, delete_after=10)

    @app_commands.command()
    @ensure_response()
    async def clear(self, itc: discord.Interaction):
        """Resume the bot"""
        server = await m.DiscordServer.from_discord_guild(itc.guild)
        await server.clear()
        await safe_response(itc, 'Cleared the bot', ephemeral=True, delete_after=10)
