"""Playlist model"""

import discord
from django.db import models

from . import filters as flt
from .through_objects import PlaylistThrough
from .utils import (extract_server_user_from_itc_async,
                    with_discord_server_async, with_discord_user_async)
from .yt_song import YTSong


class Playlist(models.Model):
    """Playlist model"""
    name = models.CharField(max_length=255)
    songs = models.ManyToManyField('YTSong', through=PlaylistThrough, related_name='playlists')

    server = models.ForeignKey('DiscordServer', on_delete=models.CASCADE)
    owner = models.ForeignKey('DiscordUser', on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    @with_discord_server_async
    @with_discord_user_async
    async def create_playlist(cls, name: str, *, server: 'DiscordServer', user: 'DiscordUser'):
        """Create a playlist"""
        q = cls.objects
        q = q.filter(server=server, owner=user, name=name)
        if await q.aexists():
            return None
        return await cls.objects.acreate(name=name, server=server, owner=user)

    @classmethod
    @extract_server_user_from_itc_async
    async def get_playlists(cls, *, itc: discord.Interaction, server: 'DiscordServer', user: 'DiscordUser'):
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
            asc: str = None,
            filter_title: str = None
        ) -> list['YTSong']:
        """Return N songs from the playlist with custom sorting"""
        q = self.songs

        return await flt.get_all_songs(
            query=q,
            limit=n,
            sorting=sorting,
            asc=asc,
            filter_title=filter_title,
            server_id=self.server_id
        )

    async def add_song(self, song: 'YTSong', order: int = None) -> bool:
        """Add a song to the playlist"""
        if order is None:
            order = await self.songs.acount()
        if await PlaylistThrough.objects.filter(playlist=self, song=song).aexists():
            return False
        await PlaylistThrough.objects.acreate(playlist=self, song=song, order=order)
        return True

    async def remove_song(self, song: 'YTSong') -> bool:
        """Remove a song from the playlist"""
        if not await PlaylistThrough.objects.filter(playlist=self, song=song).aexists():
            return False
        await PlaylistThrough.objects.filter(playlist=self, song=song).adelete()
        return True

    async def add_song_multiple(self, songs: list['YTSong']):
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
