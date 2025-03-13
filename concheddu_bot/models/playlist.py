"""Playlist model"""

import discord
from django.db import models

from . import filters as flt
from .discord import DiscordServer, DiscordUser
from .through_objects import PlaylistThrough
from .yt_song import YTSong


class Playlist(models.Model):
    """Playlist model"""
    name = models.CharField(max_length=255)
    songs = models.ManyToManyField('YTSong', through=PlaylistThrough, related_name='playlists')

    server = models.ForeignKey('DiscordServer', on_delete=models.CASCADE)
    owner = models.ForeignKey('DiscordUser', on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    async def create_playlist(cls, name: str, *, server: discord.Guild, user: discord.User | discord.Member):
        """Create a playlist"""
        user = await DiscordUser.from_discord_user(user)
        server = await DiscordServer.from_discord_guild(server)
        q = cls.objects
        q = q.filter(server=server, owner=user, name=name)
        if await q.aexists():
            return None
        return await cls.objects.acreate(name=name, server=server, owner=user)

    @classmethod
    async def get_playlists(cls, *, itc: discord.Interaction):
        """Return the playlists"""
        res = []
        server = await DiscordServer.from_discord_guild(itc.guild)
        # user = await DiscordUser.from_discord_user(itc.user)
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
