# pylint: skip-file
import asyncio
import logging
import os
import urllib

import discord
import yt_dlp
from ffmpeg_normalize import FFmpegNormalize

from .semaphores import SEMAPHORE_DOWNLOAD, SEMAPHORE_FFMPEG

FORMAT = os.getenv('BOT_YTDL_FORMAT', 'worstaudio')
AUDIO_DIR = os.getenv('BOT_AUDIO_DIR', './dl')
# FFMPEG_OPTIONS = os.getenv('BOT_FFMPEG_OPTIONS', '-vn')
MAX_DURATION = int(os.getenv('BOT_MAX_DURATION', 7*60))
FFMPEG_OPTIONS = os.getenv('BOT_FFMPEG_OPTIONS', '')
NORMALIZE = os.getenv('BOT_NORMALIZE', 'True').lower() in ['true', '1', 't', 'y', 'yes']
NORMALIZE_CODEC = os.getenv('BOT_NORMALIZE_CODEC', 'aac')
NORMALIZE_EXT = os.getenv('BOT_NORMALIZE_EXT', 'mkv')

logger = logging.getLogger('bot')

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

    @classmethod
    def from_url(cls, url, data=None, *, loop=None):
        """Create a YTDLSource from a URL"""
        logger.debug(f'YTDLSource.from_url: {url}')
        return cls(url=url, data=data)

    @classmethod
    def from_path(cls, filename, metadata):
        """Create a YTDLSource from a path"""
        logger.debug(f'YTDLSource.from_path: {filename}')
        if filename is None or not os.path.exists(filename):
            logger.error(f'File {filename} does not exist')
            return None
        res = cls(path=filename, data=metadata)
        return res

    def download(self):
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

    def normalize(self, *, loop = None):
        """Normalize the audio"""
        if not NORMALIZE:
            logger.debug(f'Normalization disabled {self.path}')
            return

        name, ext = os.path.splitext(self.path)
        fname = os.path.basename(name)
        outfile = os.path.join(AUDIO_DIR, f'{fname}.norm.{NORMALIZE_EXT}')
        if os.path.exists(outfile):
            logger.debug(f'Normalized file already exists {outfile}')
            self.path_norm = outfile
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

    async def get_info(self) -> dict:
        """Get the Youtube info from a URL"""
        logger.debug(f'YTDLSource.get_info: {self.url}')
        if not self.data:
            if self.url is None:
                raise ValueError('No URL')
            with SEMAPHORE_DOWNLOAD:
                loop = asyncio.get_event_loop()
                data = await loop.run_in_executor(None, lambda: ytdl.extract_info(self.url, download=False))
            if 'entries' in data:
                # take first item from a playlist
                data = data['entries'][0]
            self.data = data

        self.path = self.data['local_path'] = ytdl.prepare_filename(self.data)
        return self.data

    def get_source(self) -> discord.AudioSource:
        if self.source is None:
            if self.path is None:
                raise ValueError('No path')
            self.source = audio_class(self.path_norm or self.path, **ffmpeg_options)
        return self.source

    @property
    def title(self):
        return self.data['title']

    @property
    def duration(self):
        return self.data['duration']

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
