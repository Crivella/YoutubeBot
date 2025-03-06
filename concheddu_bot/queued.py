"""Global runtime server variables."""
import asyncio
import logging
from collections import defaultdict

import discord

from .bot.utils import safe_disconnect

logger = logging.getLogger('bot')

class Player:
    def __init__(self):
        self.queue = Queue()
        self.playing: bool = False
        # self.server: discord.Guild = None
        self.channel: discord.VoiceChannel = None
        self.client: discord.VoiceClient = None

    async def add_song(self, source: discord.AudioSource, user: discord.Member):
        """Add a song to the queue"""
        self.queue.append((source, user))
        # if not self.playing:
        #     self.play()

    def notify(self, error = None):
        """Notify the player"""
        if error:
            logger.error(f'Error in notify: {error}')
            return
        if not self.client:
            logger.debug('Notifying without a client')
            return
        self.queue.go_next()
        asyncio.run_coroutine_threadsafe(self.play(), asyncio.get_event_loop())

    async def clear(self):
        """Clear the queue"""
        self.queue.clear()
        await self.stop()
        # self.channel = None

    async def stop(self):
        """Stop the player"""
        try:
            await safe_disconnect(self.client)
        except Exception as e:
            logger.error(e, exc_info=True)
        else:
            self.playing = False
            self.client = None
            self.channel = None

    async def play(self):
        """Play the player"""
        song, user = self.queue.get_current()
        if not self.client:
            self.channel = user.voice.channel
            if not self.channel:
                logger.warning('No channel to connect to')
                return
            self.client = await self.channel.connect()

        if song:
            self.client.play(song, after=self.notify)
            self.playing = True
        else:
            await self.stop()

    def resume(self):
        """Resume the player"""
        # self.playing = True
        self.play()

class Queue(list):
    def __init__(self):
        self.idx: int = 0
        self.loop_all: bool = False
        self.loop_one: bool = False

    def get_current(self):
        if self.idx >= len(self):
            return None
        return self[self.idx]

    def go_next(self, val = 1):
        if not self.loop_one:
            self.idx += val
        if self.idx < 0:
            self.idx = 0
        if self.idx >= len(self):
            if self.loop_all:
                self.idx = 0
            else:
                self.idx = len(self)

    def jump_relative(self, value: int):
        """Jump to a position in the queue relative to the current position"""
        self.go_next(value)

    def clear(self):
        super().clear()
        self.idx = 0
        self.loop_all = False
        self.loop_one = False


memo: dict[int, Player] = defaultdict(Player)


class QueuedServer:
    @property
    def player(self) -> Player:
        """Return the queue"""
        return memo[self.discord_id]

    @property
    def playing(self) -> bool:
        """Return the playing status"""
        return self.player.playing
    @playing.setter
    def playing(self, value: bool):
        """Set the playing status"""
        self.player.playing = value

    @property
    def channel(self) -> discord.VoiceChannel:
        """Return the voice channel"""
        return self.player.channel
    @channel.setter
    def channel(self, value: discord.VoiceChannel):
        """Set the voice channel"""
        self.player.channel = value

    # def get_next_song(self):
    #     """Return the next song"""
    #     self.player.queue.go_next()
    #     return self.player.queue.get_current()

    def add_song(self, song):
        """Add a song to the queue"""
        self.player.add_song(song)

    # def jump_relative(self, pos: int):
    #     """Jump to a position in the queue"""
    #     self.player.queue.jump_relative(pos)

    def stop(self):
        """Clean the queue"""
        self.player.stop()
        # self.player.idx = 0
        # self.playing = False
        # self.channel = None

    def resume(self):
        """Resume the queue"""
        self.player.resume()

    def clear(self):
        """Clear the queue"""
        self.player.clear()
