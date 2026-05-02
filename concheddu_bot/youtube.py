# pylint: skip-file
import asyncio
import logging
import os
import re
import urllib
from typing import Awaitable, Optional, Self

import discord
import yt_dlp
from ffmpeg_normalize import FFmpegNormalize

from .semaphores import SEMAPHORE_DOWNLOAD, SEMAPHORE_FFMPEG

FORMAT = os.getenv('BOT_YTDL_FORMAT', 'worstaudio')
AUDIO_DIR = os.getenv('BOT_AUDIO_DIR', './dl')
MAX_DURATION = int(os.getenv('BOT_MAX_DURATION', 7*60))
FFMPEG_OPTIONS = os.getenv('BOT_FFMPEG_OPTIONS', '-vn')
NORMALIZE = os.getenv('BOT_NORMALIZE', 'True').lower() in ['true', '1', 't', 'y', 'yes']
NORMALIZE_CODEC = os.getenv('BOT_NORMALIZE_CODEC', 'aac')
NORMALIZE_EXT = os.getenv('BOT_NORMALIZE_EXT', 'mkv')

logger = logging.getLogger('bot')

thumbnail_rgx = re.compile(r'/sd[0-9a-z]+\.webp$')

THUMB_DIR = os.path.join(AUDIO_DIR, 'thumbs')

if not os.path.exists(THUMB_DIR):
    os.makedirs(THUMB_DIR)

ytdl = yt_dlp.YoutubeDL({
    'format': FORMAT,
    # 'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'ignoreerrors': False,
    'logtostderr': False,
    # 'quiet': True,
    # 'no_warnings': True,
    # 'default_search': 'auto',

    'source_address': '0.0.0.0',
    'default_search': 'ytsearch',
    'outtmpl': '%(id)s.%(ext)s',
    'noplaylist': True,
    'allow_playlist_files': False,
    'nocheckcertificate': True,
    'quiet': True,
    'no_warnings': True,
    # 'progress_hooks': [lambda info, ctx=ctx: video_progress_hook(ctx, info)],
    # 'match_filter': lambda info, incomplete, will_need_search=will_need_search, ctx=ctx: start_hook(ctx, info, incomplete, will_need_search),
    'paths': {'home': AUDIO_DIR},
})


ffmpeg_options = {
    'options': FFMPEG_OPTIONS,
    'before_options': '',
}


ffmpeg_normalize_options = {
    # 'audio_codec': 'libopus',
    'audio_codec': NORMALIZE_CODEC,
}

# audio_class = discord.FFmpegOpusAudio
audio_class = discord.FFmpegPCMAudio


class YTDLSource():
    def __init__(self, url = None, data = None, path = None, *, volume=0.5):
        self.url = url
        self.data = data
        self.path = path
        self.path_norm = None
        self.source = None

        self.ff_opts = ffmpeg_options.copy()

    @classmethod
    async def youtube_search(cls, query: str, max_results: int = 5,  *, loop = None) -> list[Self]:
        """Search YouTube for a query and return a list of results"""
        query_str = f'ytsearch{max_results}:{query}'
        logger.debug(f'YTDLSource.youtube_search: {query} -> {query_str}')
        async with SEMAPHORE_DOWNLOAD:
            loop = loop or asyncio.get_event_loop()
            search_result = await loop.run_in_executor(None, lambda: ytdl.extract_info(query_str, download=False))
        entries = search_result.setdefault('entries', [])
        if len(entries) != max_results:
            logger.warning(f'Expected {max_results} results, got {len(entries)}')

        res = []
        for entry in entries:
            url = entry.get('webpage_url', None) or entry.get('url')
            res.append(cls.from_url(url, data=entry))
        return res[:max_results]

    @classmethod
    def from_url(cls, url, data=None, *, loop=None):
        """Create a YTDLSource from a URL"""
        logger.debug(f'YTDLSource.from_url: {url}')
        return cls(url=url, data=data)

    @classmethod
    def from_path(cls, filename, metadata) -> Optional[Self]:
        """Create a YTDLSource from a path"""
        logger.debug(f'YTDLSource.from_path: {filename}')
        if filename is None:
            logger.error(f'No filename')
            return None
        if not os.path.exists(filename):
            filename = os.path.join(AUDIO_DIR, filename)
            if not os.path.exists(filename):
                logger.error(f'File {filename} does not exist relative or absolute')
                return None
        res = cls(path=filename, data=metadata)
        return res

    def download(self) -> Optional[Awaitable]:
        """Download the audio"""
        if self.path is None:
            raise ValueError('No path')
        if os.path.exists(self.path):
            return
        return self._download()

    async def _download(self, loop=None):
        """Download the audio async"""
        async with SEMAPHORE_DOWNLOAD:
            logger.info(f'Downloading {self.url}')
            loop = loop or asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: ytdl.download(self.url))

    def get_norm_path(self):
        """Get the normalized path"""
        if self.path_norm is None:
            name, _ = os.path.splitext(self.path)
            fname = os.path.basename(name)
            self.path_norm = os.path.join(AUDIO_DIR, f'{fname}.norm.{NORMALIZE_EXT}')
        return self.path_norm

    def normalize(self, *, loop = None) -> Optional[Awaitable]:
        """Normalize the audio"""
        if not NORMALIZE:
            logger.debug(f'Normalization disabled {self.path}')
            return

        outfile = self.get_norm_path()
        if os.path.exists(outfile):
            logger.debug(f'Normalized file already exists {outfile}')
            return

        return self._normalize(self.path, outfile, loop=loop)

    async def _normalize(self, src, dst, *, loop=None):
        """Normalize the audio async"""
        async with SEMAPHORE_FFMPEG:
            logger.info(f'Normalizing {src} -> {dst}')
            try:
                norm = FFmpegNormalize(**ffmpeg_normalize_options)
                norm.add_media_file(src, dst)
                loop = loop or asyncio.get_event_loop()
                await loop.run_in_executor(None, norm.run_normalization)
            except Exception as e:
                logger.error(f'Error normalizing {src}: {e}')
            else:
                logger.info(f'Normalized {src} -> {dst}')
                self.path_norm = dst

    async def set_segment(self, start: int, end: int):
        """Set the ffmpeg options to play a segment of the audio"""
        if end > self.duration:
            raise ValueError(f'End time {end} is greater than duration {self.duration}')
        if start < 0:
            raise ValueError(f'Start time {start} is less than 0')
        if start >= end:
            raise ValueError(f'Start time {start} is greater than end time {end}')
        self.ff_opts['options'] += f' -ss {start} -to {end}'

    async def get_info(self, *, force: bool = False, loop = None) -> dict:
        """Get the Youtube info from a URL"""
        logger.debug(f'YTDLSource.get_info: {self.url}')
        if not self.data or force:
            if self.url is None:
                raise ValueError('No URL')
            async with SEMAPHORE_DOWNLOAD:
                loop = loop or asyncio.get_event_loop()
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(self.url, download=False))
            if 'entries' in data:
                # take first item from a playlist
                data = data['entries'][0]
            # data['thumbnails'] = [_['url'] for _ in data['thumbnails'] if thumbnail_rgx.search(_['url'])]
            self.data = data

        self.path = ytdl.prepare_filename(self.data)
        return self.data

    def get_source(self, audio_filter: str = None) -> discord.AudioSource:
        if audio_filter is not None and audio_filter not in self.ff_opts['options']:
            self.ff_opts['options'] += f' -af "{audio_filter}" '
        if self.source is None:
            path = self.path_norm or self.path
            if path is None:
                raise ValueError('No path')
            self.source = audio_class(path, **self.ff_opts)
        return self.source

    async def delete_files(self):
        """Delete the files"""
        if self.path is not None and os.path.exists(self.path):
            os.remove(self.path)
        path_norm = self.get_norm_path()
        if path_norm is not None and os.path.exists(path_norm):
            os.remove(self.path_norm)

    @property
    def title(self):
        return self.data['title']

    @property
    def duration(self):
        return self.data['duration']

    @property
    def youtube_id(self):
        return self.data['id']

    @staticmethod
    def get_id_from_url(url: str) -> str:
        """Get the YouTube ID from a URL

        Args:
            url (str): URL to validate

        Returns:
            str: yt_id

        Raises:
            InvalidURLError: If URL is a valid URL but not a YouTube URL
        """
        logger.debug(f'YTDLSource.get_id_from_url: {url}')
        if not urllib.parse.urlparse(url).scheme:
            return url
        if 'youtube.com' not in url:
            raise YTDLSource.InvalidURLError(f'Not a valid YouTube URL')
        ytid = url
        try:
            ytid = ytid.split('watch?v=')[1]
            ytid = ytid.split('&')[0]
        except IndexError:
            raise YTDLSource.InvalidURLError(f'Not a valid YouTube URL')
        return ytid

    class MaxDurationError(Exception):
        pass

    class InvalidURLError(Exception):
        pass
