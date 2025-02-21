"""Models for the bot"""
import asyncio
import urllib
from functools import wraps
from typing import Union

import discord
from django.db import models

from .queued import QueuedServer
from .youtube import YTDLSource


async def safe_disconnect(connection: discord.VoiceClient):
    """Disconnect the bot from the voice channel"""
    if not connection.is_playing():
        await connection.disconnect()

def with_discord_user_async(func):
    """Decorator to add discord user to kwargs"""
    @wraps(func)
    async def wrapper(*args, user: discord.User, **kwargs):
        user_obj, _ = await DiscordUser.objects.aget_or_create(discord_id=user.id)
        if user_obj.username != user.name:
            user_obj.username = user.name
            await user_obj.asave()

        return await func(*args, user=user_obj, **kwargs)
    return wrapper

def with_discord_server_async(func):
    """Decorator to add discord server to kwargs"""
    @wraps(func)
    async def wrapper(*args, server: discord.Guild, **kwargs):
        server_obj, _ = await DiscordServer.objects.aget_or_create(discord_id=server.id)
        if server_obj.name != server.name:
            server_obj.name = server.name
            await server_obj.asave()

        return await func(*args, server=server_obj, **kwargs)
    return wrapper

memo = {}


class DiscordServer(QueuedServer, models.Model):
    """Server model"""
    name = models.CharField(max_length=255)
    discord_id = models.IntegerField()

    users = models.ManyToManyField('DiscordUser', related_name='servers')
    songs = models.ManyToManyField('YTSong', through='AddedSongEvent', related_name='servers')

    @classmethod
    async def from_discord_guild(cls, guild: discord.Guild):
        """Return the discord server"""
        server_obj, _ = await cls.objects.aget_or_create(discord_id=guild.id)
        if server_obj.name != guild.name:
            server_obj.name = guild.name
            await server_obj.asave()
        return server_obj

    async def get_all_songs(self):
        """Return all the songs in the server"""
        q = AddedSongEvent.objects
        q = q.filter(server=self)
        q = q.select_related('song')
        res = []
        async for a in q:
            res.append(a.song)
        return res

class DiscordUser(models.Model):
    """User model"""
    username = models.CharField(max_length=255)
    discord_id = models.IntegerField()

    played_songs = models.ManyToManyField('YTSong', through='PlayEvent', related_name='users')
    favorite_songs = models.ManyToManyField('YTSong', through='FavoriteSongThrough', related_name='users_favorite')

    @classmethod
    async def from_discord_user(cls, user: discord.User):
        """Return the discord user"""
        user_obj, _ = await cls.objects.aget_or_create(discord_id=user.id)
        if user_obj.username != user.name:
            user_obj.username = user.name
            await user_obj.asave()
        return user_obj

class DiscordChannel(models.Model):
    """Channel model"""
    name = models.CharField(max_length=255)
    server = models.ForeignKey(DiscordServer, on_delete=models.CASCADE)

class FavoriteSongThrough(models.Model):
    """Favorite song through model"""
    user = models.ForeignKey(DiscordUser, on_delete=models.CASCADE)
    song = models.ForeignKey('YTSong', on_delete=models.CASCADE)
    server = models.ForeignKey(DiscordServer, on_delete=models.CASCADE)

    added_date = models.DateTimeField(auto_now_add=True)

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

    added_by = models.ManyToManyField(DiscordUser, through=AddedSongEvent, related_name='added_songs')

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
    async def from_search_string(cls, search: str, *, user: DiscordUser, server: DiscordServer):
        """Return the song from search string"""
        song = None
        if urllib.parse.urlparse(search).scheme:
            if not 'youtube' in search:
                raise ValueError('Only youtube links are allowed')
            ytid = search
            ytid = ytid.split('watch?v=')[1]
            ytid = ytid.split('&')[0]
            if not ytid:
                raise ValueError('Invalid youtube link')
            song = cls.objects.get(youtube_id=ytid)
        if song is None:
            source = await YTDLSource.from_url(search, loop=asyncio.get_event_loop())
            data = source.data
            song, created = await cls.objects.aget_or_create(youtube_id=data['id'])
            if created:
                song.title = data['title']
                song.duration = data['duration']
                song.extension = data['ext']
                song.local_path = source.local_path

        if not await AddedSongEvent.objects.filter(song=song, server=server).aexists():
            await AddedSongEvent.objects.acreate(user=user, song=song, server=server)
        await song.asave()
        return song

    @property
    def url(self):
        """Return the youtube url"""
        return f'https://www.youtube.com/watch?v={self.youtube_id}'

    @property
    @with_discord_server_async
    def times_played(self, server: DiscordServer):
        """Return the number of times played"""
        q = self.play_events
        q = q.filter(server=server)
        return q.count()

    @property
    @with_discord_server_async
    def times_favorited(self, server: DiscordServer):
        """Return the number of times favorited"""
        q = self.users_favorite
        q = q.filter(server=server)
        return q.count()

    async def get_source(self):
        """Return the source"""
        metadata = {
            'title': self.title,
            'duration': self.duration,
            'id': self.youtube_id,
            'ext': self.extension
        }
        return YTDLSource.from_path(self.local_path, metadata) or await YTDLSource.from_url(self.url)

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
        await PlayEvent.objects.acreate(user=user, song=self, server=server)
        client.play(
            source,
            after = lambda e=None, c=client, u=user, s=server: self.after_play(e, c, u, s)
        )

    @staticmethod
    def after_play(error, connection: discord.VoiceClient, user: DiscordUser, server: DiscordServer):
        """After play callback"""
        if error:
            print(error)
        next_song = server.get_next_song()
        if next_song is None:
            asyncio.run_coroutine_threadsafe(safe_disconnect(connection), connection.loop)
            return
        asyncio.run_coroutine_threadsafe(
            next_song._play(connection, user=user, server=server), connection.loop
        )

    @with_discord_user_async
    @with_discord_server_async
    async def favorite(self, *, user: DiscordUser, server: DiscordServer):
        """Favorite the song"""
        if not FavoriteSongThrough.objects.filter(user=user, song=self, server=server).exists():
            FavoriteSongThrough.objects.create(user=user, song=self, server=server)

    @with_discord_server_async
    @with_discord_user_async
    async def unfavorite(self, *, user: DiscordUser, server: DiscordServer):
        """Unfavorite the song"""
        q = FavoriteSongThrough.objects.filter(user=user, song=self, server=server)
        if q.exists():
            q.delete()

    def get_top_n_played(self, n: int = 10):
        """Return the top n songs"""
        return self.objects.order_by('times_played')[:n]

    def get_top_n_favorited(self, n: int = 10):
        """Return the top n favorited songs"""
        return self.objects.order_by('times_favorited')[:n]


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
    async def get_playlists(cls, *, server: DiscordServer, user: DiscordUser):
        """Return the playlists"""
        return cls.objects.filter(server=server, owner=user).all()

    def get_songs(self, limit: int = None):
        """Return the songs in the playlist"""
        q = self.songs
        q = q.order_by('playlistthrough__order')
        if limit:
            q = q[:limit]
        return q.all()

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

    def add_song(self, song: Union[YTSong, 'str'], order=None):
        """Add a song to the playlist"""
        if order is None:
            order = self.songs.count()
        if isinstance(song, str):
            raise NotImplementedError
        PlaylistThrough.objects.create(playlist=self, song=song, order=order)

    def add_song_multiple(self, songs: list[Union[YTSong, 'str']]):
        """Add multiple songs to the playlist"""
        cnt = self.songs.count()
        for i, song in enumerate(songs):
            self.add_song(song, cnt + i)

    @property
    def songs_count(self):
        """Return the number of songs in the playlist"""
        return self.songs.count()

    @property
    def duration(self):
        """Return the duration of the playlist"""
        return sum(song.duration for song in self.songs.all())
