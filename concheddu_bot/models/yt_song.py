import logging
import re
import urllib

import discord
from django.db import models

from ..bot.utils import safe_response
from ..youtube import MAX_DURATION, YTDLSource
from . import filters as flt
from .discord import DiscordServer, DiscordUser
from .events import PlayEvent


def title_cleaner(title: str) -> str:
    """Clean the title"""
    res = title
    if res is None:
        return None
    res = re.sub(r'「[^」]*」?', '', res)
    res = re.sub(r'『[^』]*』?', '', res)
    res = re.sub(r'\[[^\]]*\] ?', '', res)
    res = re.sub(r'creditless', '', res, flags=re.I)
    res = re.sub(r'4K ?', '', res, flags=re.I)
    res = re.sub(r'1080p ?', '', res, flags=re.I)
    res = re.sub(r'U?HD ?', '', res, flags=re.I)
    res = re.sub(r'\d* ?FPS ?', '', res, flags=re.I)
    return res.strip()

logger = logging.getLogger('bot')

class YTSong(models.Model):
    """Youtube song model"""
    original_title = models.CharField(max_length=255, null=True)
    manual_title = models.CharField(max_length=255, null=True)

    youtube_id = models.CharField(max_length=128, unique=True)
    extension = models.CharField(max_length=16, null=True)
    duration = models.IntegerField(null=True)

    times_answered = models.IntegerField(default=0)
    times_guessed = models.IntegerField(default=0)

    @property
    def title(self):
        """Return the title"""
        if not hasattr(self, '_title') or self._title is None:
            res = self.manual_title or self.original_title
            if isinstance(res, str):
                res = title_cleaner(res)
            self._title = res
        else:
            res = self._title
        return str(res)
    @title.setter
    def title(self, value):
        self._title = title_cleaner(value)

    class MaxDurationError(Exception):
        """Max duration error"""

    @staticmethod
    async def get_last_played(*, server: discord.Guild) -> 'YTSong':
        """Return the last played song"""
        logger.debug(f'Getting last played song on {server.name}')
        server = await DiscordServer.from_discord_guild(server)
        q = PlayEvent.objects
        q = q.filter(server=server)
        q = q.order_by('date')
        q = q.select_related('song')
        event = await q.alast()
        return event.song

    @classmethod
    async def from_youtube_id(cls, ytid: str) -> 'YTSong':
        """Return the song from search string"""
        logger.debug(f'Getting song from youtube id {ytid}')
        song = None
        q = cls.objects
        q = q.filter(youtube_id=ytid)
        if await q.aexists():
            song = await q.aget()
        if song is None:
            url = f'https://www.youtube.com/watch?v={ytid}'
            src = YTDLSource.from_url(url)
            data = await src.get_info()
            song, _ = await cls.objects.aget_or_create(youtube_id=data['id'])

            song.original_title = data['title'].strip()
            song.duration = data['duration']
            song.extension = data['ext']
            await song.asave()

        return song

    @classmethod
    async def from_search_string(cls, search: str) -> 'YTSong':
        """Return the song from search string"""
        logger.debug(f'Getting song from search string {search}')
        song = None
        if urllib.parse.urlparse(search).scheme:
            ytid = YTDLSource.get_id_from_url(search)
            q = cls.objects
            q = q.filter(youtube_id=ytid)
            if await q.aexists():
                song = await q.aget()
        if song is None:
            # print('search', search)
            src = YTDLSource.from_url(search)
            data = await src.get_info()

            title = data['title'].strip()
            duration = int(data['duration'])
            extension = data['ext']
            if duration > MAX_DURATION:
                raise YTSong.MaxDurationError(
                    f'The song durations {duration} exceeds the maximum duration {MAX_DURATION}'
                )
            # source = await YTDLSource.from_url(search, loop=asyncio.get_event_loop())

            # data = source.data
            song, _ = await cls.objects.aget_or_create(youtube_id=data['id'])
            song.original_title = title
            song.duration = duration
            song.extension = extension

        await song.asave()
        return song

    @property
    def url(self):
        """Return the youtube url"""
        return f'https://www.youtube.com/watch?v={self.youtube_id}'

    @property
    def metadata(self):
        """Return the metadata"""
        return {
            'title': self.title,
            'duration': self.duration,
            'ext': self.extension,
            'id': self.youtube_id,
        }

    async def get_times_played(self, *, server_id: int):
        """Return the number of times played"""
        logger.debug(f'Getting times played for {self.title} on <{server_id}>')
        q = PlayEvent.objects
        q = q.filter(song=self, server_id=server_id)
        return await q.acount()

    async def get_source(
            self, itc: discord.Interaction = None,
            start: int = None, end: int = None,
            audio_filter: str = None
            ):
        """Perform the following steps to ensure the source is fetched and ready to play:
            1. Get the source info if it's not already fetched
            2. Download the source if it's not already downloaded
            3. Normalize the source if it's not already

        Show the progress in the interaction if provided
        """
        if hasattr(self, 'source') and self.source:
            return self.source

        path = f'{self.youtube_id}.{self.extension}'
        src = YTDLSource.from_path(path, self.metadata)
        src = src or YTDLSource.from_url(self.url, self.metadata)

        await src.get_info()

        download = src.download()
        if download:
            msg = f'Downloading {self.title}'
            await safe_response(itc, msg, ephemeral=True, append=True)
            await download

        normalize = src.normalize()
        if normalize:
            msg = f'Normalizing {self.title}'
            await safe_response(itc, msg, ephemeral=True, append=True)
            await normalize

        if hasattr(self, 'start') and hasattr(self, 'end') and self.start is not None and self.end is not None:
            start = self.start
            end = self.end
            logger.debug(f'Setting segment {start} -> {end}')
            await src.set_segment(start, end)

        await safe_response(itc, f'Loaded {self.title}', ephemeral=True, append=True)

        return src.get_source(audio_filter=audio_filter)

    async def play(
            self,
            update_msg: bool = True,
            start: int = None, end: int = None,
            audio_filter: str = None,
            *,
            itc: discord.Interaction,
            **kwargs
        ):
        """Play or queue the song"""
        # Ensure the channel is extracted ASAP in case the users leaves the channel before add_source
        channel = itc.user.voice.channel
        if not channel:
            logger.error(f'User `{itc.user}` is not in a voice channel even if play is called')
            return

        self.start = start
        self.end = end

        user = await DiscordUser.from_discord_user(itc.user)
        server = await DiscordServer.from_discord_guild(itc.guild)

        async def on_play():
            # logger.debug(f'ON_PLAY: Playing {self.title} on {server.name}')
            if update_msg:
                await safe_response(itc, f'Playing {self.title}', ephemeral=True, append=True)
            await PlayEvent.objects.acreate(
                user=user, song=self, server=server,
                start=start, end=end, audio_filter=audio_filter
            )

        itc_ = itc if update_msg else None

        await self.get_source(itc=itc_)
        await server.add_source(self, itc.user, on_play, audio_filter, channel=channel)

    @classmethod
    async def get_all_songs(
            cls,
            *,
            server: discord.Guild,
            n: int = None,
            sorting: str = 'title',
            asc: str = None,
            filter_title: str = None
        ) -> list['YTSong']:
        """Return n random songs"""
        if isinstance(server, discord.Guild):
            server = await DiscordServer.from_discord_guild(server)
        elif isinstance(server, DiscordServer):
            pass
        else:
            raise ValueError(f'Invalid type for server: {type(server)}')
        logger.debug(f'Getting all songs on [{server.name}] sorted by `{sorting}`')
        q = cls.objects

        return await flt.get_all_songs(
            query=q,
            limit=n,
            server_id=server.id,
            sorting=sorting,
            asc=asc,
            filter_title=filter_title
        )

    async def delete_files(self):
        """Delete the files"""
        logger.debug(f'Deleting files for {self.title}')
        path = f'{self.youtube_id}.{self.extension}'
        src = YTDLSource.from_path(path, self.metadata)

        await src.delete_files()
