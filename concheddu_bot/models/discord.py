"""Models for the bot"""
from collections import defaultdict

import discord
from django.db import models

from ..bot.player import Player
from .events import AddedSongEvent
from .utils import logger

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

    async def add_song(self, song: 'YTSong', user: 'DiscordUser') -> bool:
        """Add a song to the server"""
        logger.debug(f'Adding song {song.title} to server {self.name}')
        q = AddedSongEvent.objects.filter(server=self, song=song)
        if not await q.aexists():
            await AddedSongEvent.objects.acreate(server=self, song=song, user=user)
            return True
        return False

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

class DiscordChannel(models.Model):
    """Channel model"""
    name = models.CharField(max_length=255)
    server = models.ForeignKey(DiscordServer, on_delete=models.CASCADE)
