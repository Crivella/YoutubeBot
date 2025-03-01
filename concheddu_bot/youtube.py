# pylint: skip-file
import asyncio
import os
import urllib

import discord
import yt_dlp
from ffmpeg_normalize import FFmpegNormalize

FORMAT = os.getenv('BOT_YTDL_FORMAT', 'worstaudio')
AUDIO_DIR = os.getenv('BOT_AUDIO_DIR', './dl')
# FFMPEG_OPTIONS = os.getenv('BOT_FFMPEG_OPTIONS', '-vn')
MAX_DURATION = int(os.getenv('BOT_MAX_DURATION', 7*60))
FFMPEG_OPTIONS = os.getenv('BOT_FFMPEG_OPTIONS', '')
NORMALIZE = os.getenv('BOT_NORMALIZE', 'True').lower() in ['true', '1', 't', 'y', 'yes']
NORMALIZE_CODEC = os.getenv('BOT_NORMALIZE_CODEC', 'aac')
NORMALIZE_EXT = os.getenv('BOT_NORMALIZE_EXT', 'mkv')

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

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)

        self.data = data

    @classmethod
    async def from_path(cls, filename, metadata):
        if filename is None or not os.path.exists(filename):
            return None
        if NORMALIZE:
            filename = await cls.normalize(filename)
        res = cls(audio_class(filename, **ffmpeg_options), data=metadata)
        return res

    @classmethod
    async def from_url(cls, url, data, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: ytdl.download(url))

        filename = ytdl.prepare_filename(data)
        if NORMALIZE:
            filename = await cls.normalize(filename)
        res = cls(audio_class(filename, **ffmpeg_options), data=data)
        return res

    @staticmethod
    async def normalize(local_path) -> bool:
        """Normalize the audio"""
        try:
            name, ext = os.path.splitext(local_path)
            fname = os.path.basename(name)
            outfile = os.path.join(AUDIO_DIR, f'{fname}.norm.{NORMALIZE_EXT}')
            if os.path.exists(outfile):
                return outfile
            norm = FFmpegNormalize(**ffmpeg_normalize_options)
            norm.add_media_file(local_path, outfile)
            norm.run_normalization()
        except Exception as e:
            print(f'Error normalizing {local_path}: {e}')
            return
        else:
            print(f'Normalized {local_path}')
        return outfile

    @staticmethod
    async def get_info(url: str):
        """Get the Youtube info from a URL"""
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]
        data['local_path'] = ytdl.prepare_filename(data)
        return data

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
