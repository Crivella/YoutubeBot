"""Global runtime server variables."""
from collections import defaultdict

import discord


class Queue(list):
    def __init__(self):
        # self.list = []
        self.playing: bool = False
        self.channel: discord.VoiceChannel = None
        self.idx: int = 0
        self.loop_all: bool = False
        self.loop_one: bool = False

    def get_next(self):
        if not self:
            return None
        if self.loop_one:
            return self[self.idx]
        self.idx += 1
        if self.idx < 0:
            self.idx = 0
        if self.idx >= len(self):
            if self.loop_all:
                self.idx = 0
            else:
                return None
        return self[self.idx]

    def jump(self, pos: int):
        """Jump to a position in the queue"""
        self.idx = pos - 1
        if self.idx >= len(self):
            self.idx = len(self) - 1
        if self.idx < 0:
            self.idx = 0

    def jump_relative(self, value: int):
        """Jump to a position in the queue relative to the current position"""
        self.idx += value - 1
        if self.idx >= len(self):
            self.idx = len(self) - 1

    def clear(self):
        super().clear()
        self.idx = 0
        self.playing = False
        self.channel = None


memo: dict[int, Queue] = defaultdict(Queue)


class QueuedServer:
    @property
    def queue(self) -> Queue:
        """Return the queue"""
        return memo[self.discord_id]

    @property
    def playing(self) -> bool:
        """Return the playing status"""
        return self.queue.playing
    @playing.setter
    def playing(self, value: bool):
        """Set the playing status"""
        self.queue.playing = value

    @property
    def channel(self) -> discord.VoiceChannel:
        """Return the voice channel"""
        return self.queue.channel
    @channel.setter
    def channel(self, value: discord.VoiceChannel):
        """Set the voice channel"""
        self.queue.channel = value

    def get_next_song(self):
        """Return the next song"""
        return self.queue.get_next()

    def add_song(self, song):
        """Add a song to the queue"""
        self.queue.append(song)

    def jump_relative(self, pos: int):
        """Jump to a position in the queue"""
        self.queue.jump_relative(pos)

    def stop(self):
        """Clean the queue"""
        self.queue.clear()
        self.queue.idx = 0
        self.playing = False
        self.channel = None
