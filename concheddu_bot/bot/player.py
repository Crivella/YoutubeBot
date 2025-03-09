"""Global runtime server variables."""
import asyncio
import logging
from functools import wraps
from typing import Callable

import discord

from ..semaphores import SEMAPHORE_FFMPEG
from .utils import safe_disconnect

logger = logging.getLogger('bot')

def with_monitor(func):
    """Decorator to add a monitor to the function"""
    @wraps(func)
    async def wrapper(cls, *args, channel: discord.VoiceChannel, **kwargs):
        if cls.monitoring_task is None or cls.monitoring_task.done():
            cls.monitoring_task = asyncio.create_task(cls.monitor())
        cls.active = True
        cls.channel = channel
        return await func(cls, *args, **kwargs)
    return wrapper

class Queue(list):
    def __init__(self):
        self.idx: int = 0
        self.loop_all: bool = False
        self.loop_one: bool = False

    def __str__(self):
        if len(self) == 0:
            return 'Empty queue'
        pre = 4
        post = 7
        res = []
        idx = self.idx

        start = max(0, idx - pre)
        end = min(len(self), idx + post)
        after = len(self) - end
        if start > 0:
            res.append(f'... ({start} songs) ...')
        for i in range(max(0, idx-pre), min(len(self), idx + post)):
            pre = '` ‣‣‣`' if idx == i else f'`{i - idx:>4d}`'
            song, user, _ = self[i]
            res.append(f'{pre} [{song.duration:>4d} s] ({user.name:>10s}) - {song.title:>40s}')
        if after > 0:
            res.append(f'... ({after} songs) ...')
        return '\n'.join(res)

    def __bool__(self):
        return len(self) > 0 and self.idx < len(self)

    def get_current(self):
        if self.idx >= len(self):
            return (None, None, None)
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

    def clear(self):
        super().clear()
        self.idx = 0
        self.loop_all = False
        self.loop_one = False

class Player:
    def __init__(self):
        self.queue = Queue()
        # self.server: discord.Guild = None
        self.channel: discord.VoiceChannel = None
        self.client: discord.VoiceClient = None

        self.active: bool = True
        self.first: bool = True
        self.monitoring_task: asyncio.Task = None

    @property
    def playing(self) -> bool:
        """Return the playing status"""
        return self.client and self.client.is_playing()

    # Rewrite monitor to be used directly without a thread
    async def monitor(self, delay: float = 0.5):
        """Monitor the player"""
        while True:
            await asyncio.sleep(delay)
            if not self.active:
                continue
            if self.playing:
                continue
            if not self.queue:
                if self.channel:
                    await self.stop()
                continue
            if not self.first:
                self.queue.go_next()
            self.first = False
            try:
                async with SEMAPHORE_FFMPEG:
                    await self.play()
                    await asyncio.sleep(0.1)
                    # Also wait here to keep the semaphore locked while playing
                    while self.playing:
                        await asyncio.sleep(delay)
            except Exception as e:
                logger.error(e, exc_info=True)

    @with_monitor
    async def add_source(self, song, user: discord.Member, on_play: Callable = None):
        """Add a song to the queue"""
        self.queue.append((song, user, on_play))

    @with_monitor
    async def jump(self, pos: int):
        """Jump to a position in the queue"""
        self.first = True
        self.queue.go_next(pos)
        await asyncio.sleep(0.1)

        if self.playing:
            self.client.stop()

    async def pause(self):
        """Pause the player"""
        self.active = False
        await asyncio.sleep(0.1)
        if self.playing:
            self.client.pause()

    async def stop(self):
        """Stop the player"""
        client = self.client
        self.first = True
        self.active = False
        self.client = None
        self.channel = None
        await asyncio.sleep(0.1)
        try:
            await safe_disconnect(client)
        except Exception as e:
            logger.error(e, exc_info=True)

    async def clear(self):
        """Clear the queue"""
        self.queue.clear()
        await self.stop()
        # self.channel = None

    async def play(self, force: bool = False):
        """Play the player"""
        if self.playing:
            if not force:
                return
            self.client.stop()

        song, user, on_play = self.queue.get_current()
        logger.debug(f'Playing {song} from `{user}`')
        if not song:
            await self.stop()
            return
        # logger.debug(f'Playing {song.title} from `{user.name}`')
        if not self.client:
            if not self.channel:
                logger.warning('No channel to connect to')
                return
            self.client = await self.channel.connect()

        try:
            source = await song.get_source()
            self.client.play(source)
        except Exception as e:
            logger.error(e, exc_info=True)
            await self.stop()
        else:
            await on_play()

    @with_monitor
    async def resume(self):
        """Resume the player"""
        if self.client.is_paused():
            self.client.resume()
