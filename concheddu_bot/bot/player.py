"""Global runtime server variables."""
import asyncio
import logging
from dataclasses import dataclass
from functools import wraps
from typing import Callable

import discord

from ..semaphores import SEMAPHORE_FFMPEG
from .buttons import CallbackButton
from .utils import safe_disconnect, safe_response

logger = logging.getLogger('bot')

# PAUSE_BUTTON_LABEL = '⏸️'
# RESUME_BUTTON_LABEL = '▶️'
PAUSE_BUTTON_LABEL = 'PAUSE'
RESUME_BUTTON_LABEL = 'RESUME'
JUMP_FORWARD_LABEL = '>>'
JUMP_BACKWARD_LABEL = '<<'
STOP_BUTTON_LABEL = 'STOP'
LOOP_ONE_LABEL = '🔁1'
LOOP_ALL_LABEL = '🔂 ALL'

GREY = discord.ButtonStyle.grey
RED = discord.ButtonStyle.red
GREEN = discord.ButtonStyle.green
BLUE = discord.ButtonStyle.blurple

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

@dataclass
class QueueObject:
    song: 'YTSong' = None
    user: discord.Member = None
    on_play: Callable = None
    afilt: str = None

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
            obj = self[i]
            res.append(f'{pre} [{obj.song.duration:>4d} s] ({obj.user.name:>10s}) - {obj.song.title:>40s}')
        if after > 0:
            res.append(f'... ({after} songs) ...')
        return '\n'.join(res)

    def __bool__(self):
        return len(self) > 0 and self.idx < len(self)

    def get_current(self):
        if self.idx >= len(self):
            return QueueObject()
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

    def is_first(self) -> bool:
        """Check if the current song is the first in the queue"""
        return self.idx == 0

    def is_last(self) -> bool:
        """Check if the current song is the last in the queue"""
        return self.idx >= len(self) - 1

    def clear(self):
        super().clear()
        self.idx = 0
        self.loop_all = False
        self.loop_one = False

class Player:
    def __init__(self):
        self.queue: Queue = Queue()
        # self.server: discord.Guild = None
        self.channel: discord.VoiceChannel = None
        self.client: discord.VoiceClient = None

        self.active: bool = True
        self.first: bool = True
        self._locked: bool = False
        self.monitoring_task: asyncio.Task = None

        # self.text_channel: discord.TextChannel = None
        self.view: discord.ui.View = None
        self.message: discord.Message = None
        self.verobse: bool = True

    @property
    def playing(self) -> bool:
        """Return the playing status"""
        return self.client and self.client.is_playing()

    @property
    def locked(self) -> bool:
        """Return the locked status"""
        return self._locked

    async def lock(self):
        """Lock the player"""
        logger.debug('Locking player')
        self._locked = True

    async def unlock(self):
        self._locked = False
        logger.debug('Unlocking player')
        if not self.queue:
            await self.stop()

    async def enable_verbose(self):
        """Enable verbose mode"""
        self.verobse = True

    async def disable_verbose(self):
        """Disable verbose mode"""
        self.verobse = False

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
                await self.stop()
                continue
            if not self.first:
                self.queue.go_next()
            self.first = False
            try:
                await self.play()
            except Exception as e:
                logger.error(e, exc_info=True)

    @with_monitor
    async def add_source(self, song, user: discord.Member, on_play: Callable = None, audio_filter: str = None):
        """Add a song to the queue"""
        self.queue.append(QueueObject(
            song=song,
            user=user,
            on_play=on_play,
            afilt=audio_filter
         ))

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

    async def delete_message(self):
        """Delete the message"""
        if self.message is None:
            return
        try:
            await self.message.delete()
        except discord.NotFound:
            pass
        except Exception as e:
            logger.error(e, exc_info=True)
        self.message = None

    async def stop(self):
        """Stop the player"""
        client = self.client
        self.first = True
        self.active = False
        await self.delete_message()
        await asyncio.sleep(0.1)
        if not self.locked:
            try:
                await safe_disconnect(client)
            except Exception as e:
                logger.error(e, exc_info=True)

    async def clear(self):
        """Clear the queue"""
        self.queue.clear()
        # TODO: Quiz relies on clear but need to maintain the player locked
        # await self.unlock()
        await self.stop()

    async def play(self, force: bool = False):
        """Play the player"""
        if self.playing:
            if not force:
                return
            self.client.stop()

        # song, user, on_play, afilt = self.queue.get_current()
        obj = self.queue.get_current()
        if not obj.song:
            await self.stop()
            return
        logger.debug(f'Playing {obj.song} from `{obj.user}`')
        # logger.debug(f'Playing {song.title} from `{user.name}`')
        if not self.client:
            if not self.channel:
                logger.warning('No channel to connect to')
                return
            self.client = await self.channel.connect()

        source = await obj.song.get_source(audio_filter=obj.afilt)
        async with SEMAPHORE_FFMPEG:
            try:
                self.client.play(source)
            except Exception as e:
                logger.error(e, exc_info=True)
                await self.stop()
            else:
                await obj.on_play()
                # Keep the semaphore locked until the song is finished
                if self.verobse:
                    await self.print_message()
                else:
                    logger.debug(f'Playing {obj.song.title} from `{obj.user.name}`')
                await asyncio.sleep(0.1)
                while self.playing:
                    await asyncio.sleep(0.5)

    def setup_view(self):
        """Setup the view for the player"""
        if self.view is None:
            self.view = discord.ui.View(timeout=None)
            self.stop_button = CallbackButton(
                label=STOP_BUTTON_LABEL,
                style=RED,
                custom_id='stop_player',
                row=0,
            )
            self.jump_button_p1 = CallbackButton(
                label=JUMP_FORWARD_LABEL,
                style=BLUE,
                custom_id='jump_player_p1',
                row=0,
            )
            self.jump_button_m1 = CallbackButton(
                label=JUMP_BACKWARD_LABEL,
                style=BLUE,
                custom_id='jump_player_m1',
                row=0,
            )
            self.pause_resume_button = CallbackButton(
                label=PAUSE_BUTTON_LABEL,
                style=GREY,
                custom_id='pause_resume_player',
                call_self=True,
            )
            self.loop_one_button = CallbackButton(
                label=LOOP_ONE_LABEL,
                style=GREY,
                custom_id='loop_one_player',
                row=1,
            )
            self.loop_all_button = CallbackButton(
                label=LOOP_ALL_LABEL,
                style=GREY,
                custom_id='loop_all_player',
                row=1,
            )

            async def jump_p1(itc: discord.Interaction):
                """Jump to the next song in the queue"""
                logger.debug(f'Jumping to next song in queue pressed by {itc.user.name}')
                await self.jump(1, channel=self.channel)
            async def jump_m1(itc: discord.Interaction):
                """Jump to the previous song in the queue"""
                logger.debug(f'Jumping to previous song in queue pressed by {itc.user.name}')
                await self.jump(-1, channel=self.channel)
            async def clear(itc: discord.Interaction):
                """Clear the queue"""
                logger.debug(f'Clearing queue pressed by {itc.user.name}')
                await self.clear()
            async def pause_resume(itc: discord.Interaction, btn: CallbackButton):
                """Pause or resume the player"""
                if self.client.is_paused():
                    logger.debug(f'Resuming player pressed by {itc.user.name}')
                    await self.resume(channel=self.channel)
                else:
                    logger.debug(f'Pausing player pressed by {itc.user.name}')
                    await self.pause()

                self.refresh_view()

                await safe_response(itc, view=self.view)

            async def loop_one(itc: discord.Interaction):
                """Loop the current song"""
                logger.debug(f'Loop one pressed by {itc.user.name}')
                self.queue.loop_one = not self.queue.loop_one
                self.refresh_view()

                await safe_response(itc, view=self.view)

            async def loop_all(itc: discord.Interaction):
                """Loop all songs in the queue"""
                logger.debug(f'Loop all pressed by {itc.user.name}')
                self.queue.loop_all = not self.queue.loop_all
                self.refresh_view()

                await safe_response(itc, view=self.view)

            self.stop_button.add_callback(clear)
            self.jump_button_p1.add_callback(jump_p1)
            self.pause_resume_button.add_callback(pause_resume)
            self.jump_button_m1.add_callback(jump_m1)
            self.loop_one_button.add_callback(loop_one)
            self.loop_all_button.add_callback(loop_all)

            self.view.add_item(self.stop_button)
            self.view.add_item(self.jump_button_m1)
            self.view.add_item(self.pause_resume_button)
            self.view.add_item(self.jump_button_p1)
            self.view.add_item(self.loop_one_button)
            self.view.add_item(self.loop_all_button)

        # Refresh the view to update the buttons
        self.refresh_view()

    def refresh_view(self):
        """Refresh the view"""
        is_paused = self.client.is_paused() if self.client else False
        self.pause_resume_button.label = PAUSE_BUTTON_LABEL if not is_paused else RESUME_BUTTON_LABEL
        self.pause_resume_button.style = GREY if not is_paused else GREEN

        self.loop_one_button.style = BLUE if self.queue.loop_one else GREY
        self.loop_all_button.style = BLUE if self.queue.loop_all else GREY

        self.jump_button_p1.disabled = self.queue.is_last()
        self.jump_button_m1.disabled = self.queue.is_first()

    async def print_message(self):
        """Print a message with the embed"""
        if not self.queue or not self.queue.get_current().song:
            return
        embed, file = await self.generate_embed()

        files = [] if file is None else [file]
        func = self.client.channel.send if self.message is None else self.message.edit
        files_arg = 'files' if self.message is None else 'attachments'

        self.setup_view()

        kwargs = {
            files_arg: files,
            'embed': embed,
            'view': self.view,
            }
        try:
            self.message = await func(**kwargs)
        except Exception as e:
            logger.error(f'Error sending/editing message: {e}', exc_info=True)
            self.message = None

    async def generate_embed(self) -> tuple[discord.Embed, discord.File]:
        """Generate an embed for the current song"""
        if not self.queue or not self.queue.get_current().song:
            return discord.Embed(title='No song playing', color=0xFF0000), None

        song = self.queue.get_current().song
        embed = discord.Embed(color=0xFF0000)
        loop_str = ''
        if self.queue.loop_all:
            loop_str = '(loop all)'
        elif self.queue.loop_one:
            loop_str = '(loop one)'
        embed.add_field(name=f'Now playing: {loop_str}', value=str(self.queue))

        thumbnails = await song.get_thumbnails()
        file = None
        if thumbnails:
            thumb = thumbnails[0]
            attach_name = f'song-{song.id}.webp'
            file = discord.File(await thumb.get_image(), filename=attach_name)
            embed.set_thumbnail(url=f'attachment://{attach_name}')

        return embed, file

    @with_monitor
    async def resume(self):
        """Resume the player"""
        if not self.client:
            raise ValueError('No client to resume')
        if self.client.is_paused():
            self.client.resume()
