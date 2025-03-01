"""Models for the bot"""
import asyncio
import os
import urllib
from functools import wraps
from typing import Union

import discord
from django.db import models

from .queued import QueuedServer
from .youtube import YTDLSource


async def safe_disconnect(connection: discord.VoiceClient):
    """Disconnect the bot from the voice channel"""
    if connection.is_playing():
        return
    guild = connection.guild
    server = await DiscordServer.from_discord_guild(guild)
    server.playing = False
    server.channel = None
    await connection.disconnect()

def with_discord_user_async(func):
    """Decorator to add discord user to kwargs"""
    @wraps(func)
    async def wrapper(*args, user, **kwargs):
        if isinstance(user, (discord.User, discord.Member)):
            user_obj = await DiscordUser.from_discord_user(user)
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
        elif isinstance(server, DiscordServer):
            server_obj = server
        else:
            raise ValueError('Invalid server type')
        return await func(*args, server=server_obj, **kwargs)
    return wrapper

memo_server: dict[int, 'DiscordServer'] = {}

class DiscordServer(QueuedServer, models.Model):
    """Server model"""
    name = models.CharField(max_length=255)
    discord_id = models.BigIntegerField()

    users = models.ManyToManyField('DiscordUser', related_name='servers')
    songs = models.ManyToManyField('YTSong', through='AddedSongEvent', related_name='servers')

    @classmethod
    async def from_discord_guild(cls, guild: discord.Guild):
        """Return the discord server"""
        if guild.id in memo_server:
            return memo_server[guild.id]

        server_obj, _ = await cls.objects.aget_or_create(discord_id=guild.id)
        if server_obj.name != guild.name:
            server_obj.name = guild.name
            await server_obj.asave()

        memo_server[guild.id] = server_obj
        return server_obj

    async def get_all_songs(self):
        """Return all the songs in the server"""
        q = AddedSongEvent.objects
        q = q.filter(server=self)
        q = q.select_related('song')
        res = []
        # https://docs.djangoproject.com/en/5.1/topics/async/#queries-the-orm
        # Weirdly there is no asynchronous all `aall` method this was the only way
        # I got this to work
        async for a in q:
            res.append(a.song)
        return res

class DiscordUser(models.Model):
    """User model"""
    username = models.CharField(max_length=255)
    discord_id = models.BigIntegerField()

    @classmethod
    async def from_discord_user(cls, user: discord.User):
        """Return the discord user"""
        user_obj, _ = await cls.objects.aget_or_create(discord_id=user.id)
        if hasattr(user, 'name') and user_obj.username != user.name:
            user_obj.username = user.name
            await user_obj.asave()
        return user_obj

    @with_discord_server_async
    async def get_played_songs(self, *, server: DiscordServer) -> list['YTSong']:
        """Return the played songs"""
        q = PlayEvent.objects
        q = q.filter(user=self, server=server)
        q = q.select_related('song')
        res = set()
        async for a in q:
            res.add(a.song)
        return list(res)

    @with_discord_server_async
    async def get_favorite_songs(self, *, server: DiscordServer) -> list['YTSong']:
        """Return the favorite songs"""
        q = FavoriteSongThrough.objects
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

class FavoriteSongThrough(models.Model):
    """Favorite song through model"""
    user = models.ForeignKey(DiscordUser, on_delete=models.CASCADE)
    song = models.ForeignKey('YTSong', on_delete=models.CASCADE)
    server = models.ForeignKey(DiscordServer, on_delete=models.CASCADE)

    date = models.DateTimeField(auto_now_add=True)

class AddedSongEvent(models.Model):
    """Added song event model"""
    song = models.ForeignKey('YTSong', on_delete=models.CASCADE)
    server = models.ForeignKey(DiscordServer, on_delete=models.CASCADE)

    user = models.ForeignKey(DiscordUser, on_delete=models.CASCADE)
    date = models.DateTimeField(auto_now_add=True)

class YTSong(models.Model):
    """Youtube song model"""
    title = models.CharField(max_length=255, null=True)
    youtube_id = models.CharField(max_length=128)
    extension = models.CharField(max_length=16, null=True)
    duration = models.IntegerField(null=True)

    local_path = models.CharField(max_length=512, null=True)

    sort_desc = {
        'title': 'Sort by title',
        'duration': 'Sort by duration',
        'last_played': 'Sort by last played',
        'times_played': 'Sort by times played',
        'times_favorited': 'Sort by times added to playlists',
        'random': 'Sort randomly',
    }

    @staticmethod
    @with_discord_server_async
    async def get_last_played(*, server: DiscordServer) -> 'YTSong':
        """Return the last played song"""
        q = PlayEvent.objects
        q = q.filter(server=server)
        q = q.order_by('date')
        q = q.select_related('song')
        event = await q.alast()
        return event.song

    @classmethod
    @with_discord_user_async
    @with_discord_server_async
    async def from_youtube_id(cls, ytid: str, *, user: DiscordUser, server: DiscordServer):
        """Return the song from search string"""
        song = None
        q = cls.objects
        q = q.filter(youtube_id=ytid)
        if await q.aexists():
            song = await q.aget()
        if song is None:
            url = f'https://www.youtube.com/watch?v={ytid}'
            data = await YTDLSource.get_info(url)
            song, _ = await cls.objects.aget_or_create(youtube_id=data['id'])

            song.title = data['title'].strip()
            song.duration = data['duration']
            song.extension = data['ext']
            song.local_path = data['local_path']
            await song.asave()

        if not await AddedSongEvent.objects.filter(song=song, server=server).aexists():
            await AddedSongEvent.objects.acreate(user=user, song=song, server=server)

        return song

    @classmethod
    @with_discord_user_async
    @with_discord_server_async
    async def from_search_string(cls, search: str, *, user: DiscordUser, server: DiscordServer):
        """Return the song from search string"""
        song = None
        if urllib.parse.urlparse(search).scheme:
            ytid = YTDLSource.get_id_from_url(search)
            q = cls.objects
            q = q.filter(youtube_id=ytid)
            if await q.aexists():
                song = await q.aget()
        if song is None:
            data = await YTDLSource.get_info(search)
            # source = await YTDLSource.from_url(search, loop=asyncio.get_event_loop())

            # data = source.data
            song, _ = await cls.objects.aget_or_create(youtube_id=data['id'])
            song.title = data['title'].strip()
            song.duration = data['duration']
            song.extension = data['ext']
            song.local_path = data['local_path']

        if not await AddedSongEvent.objects.filter(song=song, server=server).aexists():
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

    @property
    def need_download(self):
        """Return if the song needs to be downloaded"""
        return self.local_path is None or not os.path.exists(self.local_path)

    @with_discord_server_async
    async def get_times_played(self, *, server: DiscordServer):
        """Return the number of times played"""
        q = PlayEvent.objects
        q = q.filter(song=self, server=server)
        return await q.acount()

    @with_discord_server_async
    async def get_times_favorited(self, *, server: DiscordServer):
        """Return the number of times favorited"""
        q = FavoriteSongThrough.objects
        q = q.filter(song=self, server=server)
        return await q.acount()

    async def get_source(self):
        """Return the source"""
        if hasattr(self, 'source') and self.source:
            return self.source
        return (
            await YTDLSource.from_path(self.local_path, self.metadata) or
            await YTDLSource.from_url(self.url, self.metadata)
        )
    async def download(self):
        """Download the song"""
        self.source = await YTDLSource.from_url(self.url, self.metadata)

    @with_discord_user_async
    @with_discord_server_async
    async def play(self, client: discord.VoiceClient, *, user: DiscordUser, server: DiscordServer):
        """Play the song"""
        server.add_song(self)
        if not client.is_playing():
            await self._play(client, user=user, server=server)

    async def _play(self, client: discord.VoiceClient, user: DiscordUser, server: DiscordServer):
        """Play the song"""
        source = await self.get_source()
        try:
            client.play(
                source,
                after = lambda e=None, c=client, u=user, s=server: self.after_play(e, c, u, s)
            )
        except Exception as e:
            print(e)
            return
        else:
            await PlayEvent.objects.acreate(user=user, song=self, server=server)
            server.playing = True
            server.channel = client.channel

    @staticmethod
    def after_play(error, connection: discord.VoiceClient, user: DiscordUser, server: DiscordServer):
        """After play callback"""
        if error:
            print(error)
        next_song = server.get_next_song()
        if next_song is None:
            asyncio.run_coroutine_threadsafe(safe_disconnect(connection), connection.loop)
        else:
            asyncio.run_coroutine_threadsafe(
                next_song._play(connection, user=user, server=server), connection.loop
            )

    @with_discord_user_async
    @with_discord_server_async
    async def favorite_toggle(self, *, user: DiscordUser, server: DiscordServer) -> bool:
        """Toggle the favorite status"""
        q = FavoriteSongThrough.objects.filter(user=user, song=self, server=server)
        if await q.aexists():
            await q.adelete()
            return False
        else:
            await FavoriteSongThrough.objects.acreate(user=user, song=self, server=server)
            return True

    @with_discord_user_async
    @with_discord_server_async
    async def favorite(self, *, user: DiscordUser, server: DiscordServer):
        """Favorite the song"""
        q = FavoriteSongThrough.objects.filter(user=user, song=self, server=server)
        if not await q.aexists():
            await FavoriteSongThrough.objects.acreate(user=user, song=self, server=server)

    @with_discord_server_async
    @with_discord_user_async
    async def unfavorite(self, *, user: DiscordUser, server: DiscordServer):
        """Unfavorite the song"""
        q = FavoriteSongThrough.objects.filter(user=user, song=self, server=server)
        if await q.aexists():
            await q.adelete()

    @staticmethod
    @with_discord_server_async
    async def get_top_played(n: int = None, *, server: DiscordServer) -> list['YTSong']:
        """Return the top n songs"""
        q = YTSong.objects
        q = q.filter(playevent__server=server)
        q = q.annotate(times_played=models.Count('playevent'))
        q = q.order_by('-times_played')
        if n:
            q = q[:n]
        return [a async for a in q]

    @staticmethod
    @with_discord_server_async
    async def get_top_favorited(n: int = None, *, server: DiscordServer) -> list['YTSong']:
        """Return the top n favorited songs"""
        q = YTSong.objects
        q = q.filter(favoritesongthrough__server=server)
        q = q.annotate(times_favorited=models.Count('favoritesongthrough'))
        q = q.order_by('-times_favorited')
        if n:
            q = q[:n]
        return [a async for a in q]

    @staticmethod
    async def get_all_songs_lp(server: DiscordServer) -> models.QuerySet:
        """Return a queryset of all songs ordered by last played on a server"""
        q = PlayEvent.objects
        q = q.filter(server=server)
        q = q.values('song')
        # q = q.select_related('song')
        q = q.annotate(last_played=models.Max('date'))
        q = q.order_by('-last_played')
        return q

    @staticmethod
    async def get_all_songs_tp(server: DiscordServer) -> models.QuerySet:
        """Return a queryset of all songs ordered by times played on a server"""
        q = PlayEvent.objects
        q = q.filter(server=server)
        q = q.values('song')
        # q = q.select_related('song')
        q = q.annotate(times_played=models.Count('song'))
        q = q.order_by('-times_played')
        return q

    @staticmethod
    async def get_all_songs_pl(server: DiscordServer) -> models.QuerySet:
        """Return a queryset of all songs ordered by times added to playlists on a server"""
        q = PlaylistThrough.objects
        q = q.filter(playlist__server=server)
        q = q.values('song')
        # q = q.select_related('song')
        q = q.annotate(time_added=models.Count('song'))
        q = q.order_by('-time_added')
        return q

    @staticmethod
    async def get_all_songs_title(server: DiscordServer) -> models.QuerySet:
        """Return a queryset of all songs ordered by title on a server"""
        q = YTSong.objects
        q = q.filter(servers=server)
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
    async def get_all_songs(*, n: int = None, server: DiscordServer, sorting: str = 'title') -> list['YTSong']:
        """Return n random songs"""
        q = await YTSong.sort_map[sorting](server)
        if n:
            q = q[:n]

        res = [a async for a in q]

        if res and isinstance(res[0], dict):
            res = [await YTSong.objects.aget(id=a['song']) for a in res]

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
    @with_discord_server_async
    @with_discord_user_async
    async def get_playlists(cls, *, server: DiscordServer, user: DiscordUser):
        """Return the playlists"""
        return cls.objects.filter(server=server, owner=user).all()

    async def get_songs(self, limit: int = None):
        """Return the songs in the playlist"""
        q = PlaylistThrough.objects
        q = q.filter(playlist=self)
        q = q.select_related('song')
        if limit:
            q = q[:limit]
        return [a.song async for a in q]

    def get_songs_order_dates(self, limit: int = None):
        """Return the songs in the playlist ordered by date"""
        q = self.songs
        q = q.order_by('playlistthrough__added_date')
        if limit:
            q = q[:limit]
        return q.all()

    def get_songs_order_times_played(self, limit: int = None):
        """Return the songs in the playlist ordered by times played"""
        q = self.songs
        q = q.annotate(times_played=models.Count('play_events'))
        q = q.order_by('times_played')
        if limit:
            q = q[:limit]
        return q.all()

    def get_songs_order_random(self, limit: int = None):
        """Return the songs in the playlist ordered randomly"""
        q = self.songs
        q = q.order_by('?')
        if limit:
            q = q[:limit]
        return q.all()

    async def add_song(self, song: Union[YTSong, 'str'], order: int = None):
        """Add a song to the playlist"""
        if order is None:
            order = await self.songs.acount()
        if isinstance(song, str):
            raise NotImplementedError
        await PlaylistThrough.objects.acreate(playlist=self, song=song, order=order)

    async def add_song_multiple(self, songs: list[Union[YTSong, 'str']]):
        """Add multiple songs to the playlist"""
        cnt = await self.songs.acount()
        for i, song in enumerate(songs):
            await self.add_song(song, cnt + i)

    # @property
    # def songs_count(self):
    #     """Return the number of songs in the playlist"""
    #     return self.songs.count()

    async def get_song_count(self):
        """Return the number of songs in the playlist"""
        return await self.songs.acount()

    async def get_duration(self):
        """Return the duration of the playlist"""
        songs = await self.get_songs()
        return sum(song.duration for song in songs)

    # @property
    # def duration(self):
    #     """Return the duration of the playlist"""
    #     q = PlaylistThrough.objects
    #     q = q.filter(playlist=self)
    #     q = q.select_related('song')
    #     return sum(a.song.duration async for a in q.all())
