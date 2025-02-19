# pylint: skip-file
import asyncio
import os

import discord
import youtube_dl

FORMAT = os.getenv('BOT_YTDL_FORMAT', 'bestaudio')
AUDIO_DIR = os.getenv('BOT_AUDIO_DIR', './dl')
FFMPEG_OPTIONS = os.getenv('BOT_FFMPEG_OPTIONS', '-vn')

ytdl = youtube_dl.YoutubeDL({
    'format': FORMAT,
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',

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

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)

        self.data = data

        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)
