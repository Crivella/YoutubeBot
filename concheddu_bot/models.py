"""Models for the bot"""
import asyncio
from functools import wraps
from typing import Union

import discord
from django.db import models


def with_discord_user_async(func):
    """Decorator to add discord user to kwargs"""
    @wraps(func)
    async def wrapper(self, *args, user: discord.User, **kwargs):
        user_obj, _ = await DiscordUser.objects.aget_or_create(discord_id=user.id)
        if user_obj.username != user.name:
            user_obj.username = user.name
            await user_obj.asave()

        return await func(self, *args, user=user_obj, **kwargs)
    return wrapper

def with_dicord_server_async(func):
    """Decorator to add discord server to kwargs"""
    @wraps(func)
    async def wrapper(self, *args, server: discord.Guild, **kwargs):
        server_obj, _ = await DiscordServer.objects.aget_or_create(discord_id=server.id)
        if server_obj.name != server.name:
            server_obj.name = server.name
            await server_obj.asave()

        return await func(self, *args, server=server_obj, **kwargs)
    return wrapper

class DiscordServer(models.Model):
    """Server model"""
    name = models.CharField(max_length=255)
    discord_id = models.IntegerField()

    users = models.ManyToManyField('DiscordUser', related_name='servers')

class DiscordUser(models.Model):
    """User model"""
    username = models.CharField(max_length=255)
    discord_id = models.IntegerField()

    played_songs = models.ManyToManyField('YTSong', through='PlayEvent', related_name='users')
    favorite_songs = models.ManyToManyField('YTSong', through='FavoriteSongThrough', related_name='users_favorite')

class DiscordChannel(models.Model):
    """Channel model"""
    name = models.CharField(max_length=255)
    server = models.ForeignKey(DiscordServer, on_delete=models.CASCADE)

class FavoriteSongThrough(models.Model):
    """Favorite song through model"""
    user = models.ForeignKey(DiscordUser, on_delete=models.CASCADE)
    song = models.ForeignKey('YTSong', on_delete=models.CASCADE)

    added_date = models.DateTimeField(auto_now_add=True)


class YTSong(models.Model):
    """Youtube song model"""
    title = models.CharField(max_length=255, null=True)
    youtube_id = models.CharField(max_length=128)
    extension = models.CharField(max_length=16, null=True)
    duration = models.IntegerField(null=True)

    local_path = models.CharField(max_length=512, null=True)

    times_played = models.IntegerField(default=0)
    times_favorited = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def url(self):
        """Return the youtube url"""
        return f'https://www.youtube.com/watch?v={self.youtube_id}'

    @classmethod
    def last_played(cls):
        """Return the last played song"""
        return cls.play_events.order_by('date').last()

    @with_discord_user_async
    async def play(self, *, user: DiscordUser):
        """Play the song"""
        await PlayEvent.objects.acreate(user=user, song=self)
        self.times_played += 1
        await self.asave()

    def favorite(self, user: DiscordUser):
        """Favorite the song"""
        if not FavoriteSongThrough.objects.filter(user=user, song=self).exists():
            FavoriteSongThrough.objects.create(user=user, song=self)
            self.times_favorited += 1

    def unfavorite(self, user: DiscordUser):
        """Unfavorite the song"""
        q = FavoriteSongThrough.objects.filter(user=user, song=self)
        if q.exists():
            q.delete()
            self.times_favorited -= 1

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
    @with_dicord_server_async
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
    def get_songs_count(self):
        """Return the number of songs in the playlist"""
        return self.songs.count()

    @property
    def get_duration(self):
        """Return the duration of the playlist"""
        return sum(song.duration for song in self.songs.all())
