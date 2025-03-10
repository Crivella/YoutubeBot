"""Models for the bot"""
import logging
import re
import urllib
from collections import defaultdict
from functools import wraps
from typing import Union

import discord
from django.db import models

from .bot.player import Player
from .bot.utils import safe_response
from .youtube import MAX_DURATION, YTDLSource

logger = logging.getLogger('bot')

def title_cleaner(title: str) -> str:
    """Clean the title"""
    res = title
    res = re.sub(r'「[^」]*」?', '', res)
    res = re.sub(r'『[^』]*』?', '', res)
    res = re.sub(r'\[[^\]]*\] ?', '', res)
    res = re.sub(r'creditless', '', res, flags=re.I)
    res = re.sub(r'4K ?', '', res, flags=re.I)
    res = re.sub(r'1080p ?', '', res, flags=re.I)
    res = re.sub(r'U?HD ?', '', res, flags=re.I)
    res = re.sub(r'\d* ?FPS ?', '', res, flags=re.I)
    return res


def extract_server_user_from_itc_async(func):
    """Decorator to extract server and user from interaction"""
    @wraps(func)
    async def wrapper(self, *args, itc: discord.Interaction, **kwargs):
        server = await DiscordServer.from_discord_guild(itc.guild)
        user = await DiscordUser.from_discord_user(itc.user)
        user.dc = itc.user
        return await func(self, itc=itc, server=server, user=user, *args, **kwargs)

    return wrapper

def with_discord_user_async(func):
    """Decorator to add discord user to kwargs"""
    @wraps(func)
    async def wrapper(*args, user, **kwargs):
        if isinstance(user, (discord.User, discord.Member)):
            user_obj = await DiscordUser.from_discord_user(user)
            user_obj.dc = user
        elif isinstance(user, DiscordUser):
            user_obj = user
        else:
            raise ValueError(f'Invalid user type {type(user)}')
        return await func(*args, user=user_obj, **kwargs)
    return wrapper

def with_discord_server_async(func):
    """Decorator to add discord server to kwargs"""
    @wraps(func)
    async def wrapper(*args, server, **kwargs):
        if isinstance(server, discord.Guild):
            server_obj = await DiscordServer.from_discord_guild(server)
            server_obj.dc = server
        elif isinstance(server, DiscordServer):
            server_obj = server
        else:
            raise ValueError('Invalid server type')
        return await func(*args, server=server_obj, **kwargs)
    return wrapper

memo_server: dict[int, 'DiscordServer'] = {}
memo_plater: dict[int, 'Player'] = defaultdict(Player)

class DiscordServer(models.Model):
    """Server model"""
    name = models.CharField(max_length=255)
    discord_id = models.BigIntegerField()

    users = models.ManyToManyField('DiscordUser', related_name='servers')
    songs = models.ManyToManyField('YTSong', through='AddedSongEvent', related_name='servers')

    dc: discord.Guild = None

    @classmethod
    async def from_discord_guild(cls, guild: discord.Guild):
        """Return the discord server"""
        logger.debug(f'Getting server from {guild.name}')
        if guild.id in memo_server:
            return memo_server[guild.id]

        server_obj, _ = await cls.objects.aget_or_create(discord_id=guild.id)
        if server_obj.name != guild.name:
            server_obj.name = guild.name
            await server_obj.asave()

        memo_server[guild.id] = server_obj
        return server_obj

    @property
    def player(self) -> Player:
        """Return the queue"""
        return memo_plater[self.discord_id]

    @property
    def playing(self) -> bool:
        """Return the playing status"""
        return self.player.playing

    @property
    def channel(self) -> discord.VoiceChannel:
        """Return the voice channel"""
        return self.player.channel

    async def add_source(self, *args, **kwargs):
        """Add a song to the queue"""
        await self.player.add_source(*args, **kwargs)

    async def jump(self, pos: int, channel: discord.VoiceChannel):
        """Jump to a position in the queue"""
        await self.player.jump(pos, channel=channel)

    async def stop(self):
        """Clean the queue"""
        await self.player.stop()

    async def pause(self):
        """Pause the queue"""
        await self.player.pause()

    async def resume(self, channel: discord.VoiceChannel):
        """Resume the queue"""
        await self.player.resume(channel=channel)

    async def clear(self):
        """Clear the queue"""
        await self.player.clear()

class DiscordUser(models.Model):
    """User model"""
    username = models.CharField(max_length=255)
    discord_id = models.BigIntegerField()

    dc: discord.User | discord.Member = None

    @classmethod
    async def from_discord_user(cls, user: discord.User):
        """Return the discord user"""
        logger.debug(f'Getting user from {user.name}')
        user_obj, _ = await cls.objects.aget_or_create(discord_id=user.id)
        if hasattr(user, 'name') and user_obj.username != user.name:
            user_obj.username = user.name
            await user_obj.asave()
        return user_obj

    @with_discord_server_async
    async def get_played_songs(self, *, server: DiscordServer) -> list['YTSong']:
        """Return the played songs"""
        logger.debug(f'Getting played songs for {self.username} on {server.name}')
        q = PlayEvent.objects
        q = q.filter(user=self, server=server)
        q = q.select_related('song')
        res = set()
        async for a in q:
            res.add(a.song)
        return list(res)

class DiscordChannel(models.Model):
    """Channel model"""
    name = models.CharField(max_length=255)
    server = models.ForeignKey(DiscordServer, on_delete=models.CASCADE)

class AddedSongEvent(models.Model):
    """Added song event model"""
    song = models.ForeignKey('YTSong', on_delete=models.CASCADE)
    server = models.ForeignKey(DiscordServer, on_delete=models.CASCADE)

    user = models.ForeignKey(DiscordUser, on_delete=models.CASCADE)
    date = models.DateTimeField(auto_now_add=True)

class GuessSongEvent(models.Model):
    """Guess song event model"""
    real_song = models.ForeignKey('YTSong', on_delete=models.CASCADE, related_name='+')
    guessed_song = models.ForeignKey('YTSong', on_delete=models.CASCADE, related_name='+')

    start = models.IntegerField(null=True)
    end = models.IntegerField(null=True)
    num_choices = models.IntegerField(null=True)

    user = models.ForeignKey(DiscordUser, on_delete=models.CASCADE, null=True, default=None, related_name='song_guesses')
    date = models.DateTimeField(auto_now_add=True)

    def __bool__(self):
        return self.real_song_id == self.guessed_song_id


class YTSong(models.Model):
    """Youtube song model"""
    original_title = models.CharField(max_length=255, null=True)
    manual_title = models.CharField(max_length=255, null=True)

    youtube_id = models.CharField(max_length=128, unique=True)
    extension = models.CharField(max_length=16, null=True)
    duration = models.IntegerField(null=True)

    times_answered = models.IntegerField(default=0)
    times_guessed = models.IntegerField(default=0)

    sort_desc = {
        'title': 'Sort by title',
        'duration': 'Sort by duration',
        'last_played': 'Sort by last played',
        'times_played': 'Sort by times played',
        'times_favorited': 'Sort by times added to playlists',
        'random': 'Sort randomly',
    }

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
        self._title = value

    class MaxDurationError(Exception):
        """Max duration error"""

    @staticmethod
    @with_discord_server_async
    async def get_last_played(*, server: DiscordServer) -> 'YTSong':
        """Return the last played song"""
        logger.debug(f'Getting last played song on {server.name}')
        q = PlayEvent.objects
        q = q.filter(server=server)
        q = q.order_by('date')
        q = q.select_related('song')
        event = await q.alast()
        return event.song

    @classmethod
    @with_discord_user_async
    @with_discord_server_async
    async def from_youtube_id(cls, ytid: str, *, user: DiscordUser, server: DiscordServer) -> 'YTSong':
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

        if not await AddedSongEvent.objects.filter(song=song, server=server).aexists():
            logger.debug(f'Adding song {song.title} to {server.name}')
            await AddedSongEvent.objects.acreate(user=user, song=song, server=server)

        return song

    @classmethod
    @with_discord_user_async
    @with_discord_server_async
    async def from_search_string(cls, search: str, *, user: DiscordUser, server: DiscordServer) -> 'YTSong':
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

        if not await AddedSongEvent.objects.filter(song=song, server=server).aexists():
            logger.debug(f'Adding song {song.title} to {server.name}')
            await AddedSongEvent.objects.acreate(user=user, song=song, server=server)
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

    @with_discord_server_async
    async def get_times_played(self, *, server: DiscordServer):
        """Return the number of times played"""
        logger.debug(f'Getting times played for {self.title} on {server.name}')
        q = PlayEvent.objects
        q = q.filter(song=self, server=server)
        return await q.acount()

    async def get_source(self, itc: discord.Interaction = None, start: int = None, end: int = None):
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

        return src.get_source()

    @extract_server_user_from_itc_async
    async def play(
            self,
            update_msg: bool = True,
            start: int = None, end: int = None,
            *,
            itc: discord.Interaction, user: DiscordUser, server: DiscordServer,
            **kwargs
        ):
        """Play or queue the song"""
        # Ensure the channel is extracted ASAP in case the users leaves the channel before add_source
        channel = user.dc.voice.channel
        if not channel:
            logger.error(f'User `{user.username}` is not in a voice channel even if play is called')
            return

        self.start = start
        self.end = end

        async def on_play():
            await safe_response(itc, f'Playing {self.title}', ephemeral=True, append=True)
            await PlayEvent.objects.acreate(user=user, song=self, server=server)

        if not update_msg:
            itc = None

        await server.add_source(self, user.dc, on_play, channel=channel)

    async def guess_ytid(
            self,
            youtube_id: str, user: DiscordUser,
            start: int = None, end: int = None, num_choices: int = None
        ) -> bool:
        """Guess the song"""
        other = await YTSong.objects.aget(youtube_id=youtube_id)
        res = self.youtube_id == youtube_id
        self.times_answered += 1
        self.times_guessed += res
        await self.asave()
        await GuessSongEvent.objects.acreate(
            real_song=self, guessed_song=other, user=user,
            start=start, end=end, num_choices=num_choices
            )
        return res

    @staticmethod
    async def get_all_songs_lp(server: DiscordServer) -> models.QuerySet:
        """Return a queryset of all songs ordered by last played on a server"""
        q = YTSong.objects
        q = q.filter(servers=server)

        q = q.annotate(last_played=models.Max(models.Case(
                models.When(
                    models.Q(playevent__server=server) &
                    models.Q(playevent__song=models.F('id')),
                    then=models.F('playevent__date')
                ),
                # Default to very old date
                # Problem here is if some somengs have never been played they will have NULL
                # and will be sorted first
                default=models.Value('1970-01-01T00:00:00Z'),
                output_field=models.DateTimeField(),
            )))
        q = q.order_by('-last_played')
        return q

    @staticmethod
    async def get_all_songs_tp(server: DiscordServer) -> models.QuerySet:
        """Return a queryset of all songs ordered by times played on a server"""
        q = YTSong.objects
        q = q.filter(servers=server)
        q = q.annotate(times_played=models.Count(models.Case(
                models.When(
                    models.Q(playevent__server=server) &
                    models.Q(playevent__song=models.F('id')),
                    then=1
                ),
                output_field=models.IntegerField(),
            )))
        q = q.order_by('-times_played')
        return q

    @staticmethod
    async def get_all_songs_pl(server: DiscordServer) -> models.QuerySet:
        """Return a queryset of all songs ordered by times added to playlists on a server"""
        q = YTSong.objects
        q = q.filter(servers=server)
        q = q.annotate(times_played=models.Count(models.Case(
                models.When(
                    models.Q(playlistthrough__playlist__server=server) &
                    models.Q(playlistthrough__song=models.F('id')),
                    then=1,
                ),
                output_field=models.IntegerField(),
            )))
        q = q.order_by('-times_played')
        return q

    @staticmethod
    async def get_all_songs_title(server: DiscordServer) -> models.QuerySet:
        """Return a queryset of all songs ordered by title on a server"""
        q = YTSong.objects
        q = q.filter(servers=server)
        q = q.annotate(title=models.F('manual_title') or models.F('original_title'))
        q = q.order_by('title')
        return q

    @staticmethod
    async def get_all_songs_duration(server: DiscordServer) -> models.QuerySet:
        """Return a queryset of all songs ordered by duration on a server"""
        q = YTSong.objects
        q = q.filter(servers=server)
        q = q.order_by('-duration')
        return q

    @staticmethod
    async def get_all_songs_random(server: DiscordServer) -> models.QuerySet:
        """Return a queryset of all songs ordered randomly on a server"""
        q = YTSong.objects
        q = q.filter(servers=server)
        q = q.order_by('?')
        return q


    @staticmethod
    @with_discord_server_async
    async def get_all_songs(
            *,
            server: DiscordServer,
            n: int = None,
            sorting: str = 'title',
            filter_title: str = None
        ) -> list['YTSong']:
        """Return n random songs"""
        logger.debug(f'Getting all songs on [{server.name}] sorted by `{sorting}`')
        q = await YTSong.sort_map[sorting](server)
        if n:
            q = q[:n]

        res = [a async for a in q]

        if filter_title:
            filter_title = filter_title.lower()
            res = list(filter(lambda a: filter_title in a.title.lower(), res))

        if res and isinstance(res[0], dict):
            res = [await YTSong.objects.aget(id=a['song']) for a in res]

        for song in res:
            song.times_played_ = await song.get_times_played(server=server)

        return res

    sort_map = {
        'title': get_all_songs_title,
        'duration': get_all_songs_duration,
        'last_played': get_all_songs_lp,
        'times_played': get_all_songs_tp,
        'times_favorited': get_all_songs_pl,
        'random': get_all_songs_random,
    }


class PlayEvent(models.Model):
    """Play event model"""
    user = models.ForeignKey(DiscordUser, on_delete=models.CASCADE)
    song = models.ForeignKey(YTSong, on_delete=models.CASCADE)
    server = models.ForeignKey(DiscordServer, on_delete=models.CASCADE)

    date = models.DateTimeField(auto_now_add=True)

class PlaylistThrough(models.Model):
    """Playlist through model"""
    playlist = models.ForeignKey('Playlist', on_delete=models.CASCADE)
    song = models.ForeignKey(YTSong, on_delete=models.CASCADE)

    order = models.IntegerField()

    added_date = models.DateTimeField(auto_now_add=True)


class Playlist(models.Model):
    """Playlist model"""
    name = models.CharField(max_length=255)
    songs = models.ManyToManyField(YTSong, through=PlaylistThrough, related_name='playlists')

    server = models.ForeignKey(DiscordServer, on_delete=models.CASCADE)
    owner = models.ForeignKey(DiscordUser, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    @with_discord_server_async
    @with_discord_user_async
    async def create_playlist(cls, name: str, *, server: DiscordServer, user: DiscordUser):
        """Create a playlist"""
        q = cls.objects
        q = q.filter(server=server, owner=user, name=name)
        if await q.aexists():
            return None
        return await cls.objects.acreate(name=name, server=server, owner=user)

    @classmethod
    @extract_server_user_from_itc_async
    async def get_playlists(cls, *, itc: discord.Interaction, server: DiscordServer, user: DiscordUser):
        """Return the playlists"""
        res = []
        # async for a in cls.objects.filter(server=server, owner=user):
        async for a in cls.objects.filter(server=server):
            res.append(a)

        for playlist in res:
            playlist.song_count = await playlist.get_song_count()
            playlist.duration = await playlist.get_duration()

        return res

    async def rename(self, name: str):
        """Rename the playlist"""
        self.name = name
        await self.asave()

    async def get_all_songs(
            self,
            *,
            n: int = None,
            sorting: str = 'title',
            filter_title: str = None
        ) -> list['YTSong']:
        """Return N songs from the playlist with custom sorting"""
        q = self.songs
        q = q.annotate(title=models.F('manual_title') or models.F('original_title'))
        if filter_title:
            q = q.filter(title__icontains=filter_title)
        if sorting == 'title':
            q = q.order_by('title')
        elif sorting == 'times_played':
            server = await DiscordServer.objects.aget(id=self.server_id)
            q = q.annotate(times_played=models.Count(models.Case(
                    models.When(
                        models.Q(playevent__server=server) &
                        models.Q(playevent__song=models.F('id')),
                        then=1
                    ),
                    output_field=models.IntegerField(),
                )))
            q = q.order_by('-times_played')
        elif sorting == 'last_played':
            server = await DiscordServer.objects.aget(id=self.server_id)
            q = q.annotate(last_played=models.Max(models.Case(
                    models.When(
                        models.Q(playevent__server=server) &
                        models.Q(playevent__song=models.F('id')),
                        then=models.F('playevent__date')
                    ),
                    default=models.Value('1970-01-01T00:00:00Z'),
                    output_field=models.DateTimeField(),
                )))
            q = q.order_by('-last_played')
        elif sorting == 'random':
            q = q.order_by('?')

        if n:
            q = q[:n]

        res = [a async for a in q.all()]
        return res

    # async def get_songs_order_times_played(self, limit: int = None):
    #     """Return the songs in the playlist ordered by times played"""
    #     # Get server foreign key for async
    #     server = await DiscordServer.objects.aget(id=self.server_id)

    #     q = self.songs
    #     q = q.annotate(times_played=models.Count(models.Case(
    #             models.When(
    #                 models.Q(playevent__server=server) &
    #                 models.Q(playevent__song=models.F('id')),
    #                 then=1
    #             ),
    #             output_field=models.IntegerField(),
    #         )))
    #     q = q.order_by('-times_played')
    #     if limit:
    #         q = q[:limit]
    #     return [a async for a in q]

    # async def get_songs_order_random(self, limit: int = None):
    #     """Return the songs in the playlist ordered randomly"""
    #     q = self.songs
    #     q = q.order_by('?')
    #     if limit:
    #         q = q[:limit]
    #     return [a async for a in q.all()]

    async def add_song(self, song: YTSong, order: int = None) -> bool:
        """Add a song to the playlist"""
        if order is None:
            order = await self.songs.acount()
        if await PlaylistThrough.objects.filter(playlist=self, song=song).aexists():
            return False
        await PlaylistThrough.objects.acreate(playlist=self, song=song, order=order)
        return True

    async def remove_song(self, song: YTSong) -> bool:
        """Remove a song from the playlist"""
        if not await PlaylistThrough.objects.filter(playlist=self, song=song).aexists():
            return False
        await PlaylistThrough.objects.filter(playlist=self, song=song).adelete()
        return True

    async def add_song_multiple(self, songs: list[Union[YTSong, 'str']]):
        """Add multiple songs to the playlist"""
        cnt = await self.songs.acount()
        for i, song in enumerate(songs):
            await self.add_song(song, cnt + i)

    async def get_song_count(self):
        """Return the number of songs in the playlist"""
        return await self.songs.acount()

    async def get_duration(self):
        """Return the duration of the playlist"""
        songs = [a async for a in self.songs.all()]
        return sum(song.duration for song in songs)
