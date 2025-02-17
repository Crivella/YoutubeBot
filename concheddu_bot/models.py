"""Models for the bot"""
from django.db import models


class DiscordServer(models.Model):
    """Server model"""
    name = models.CharField(max_length=255)
    discord_id = models.CharField(max_length=255)

class DiscordUser(models.Model):
    """User model"""
    username = models.CharField(max_length=255)
    discord_id = models.CharField(max_length=255)

class DiscordGuild(models.Model):
    """Guild model"""
    name = models.CharField(max_length=255)
    discord_id = models.CharField(max_length=255)

    server = models.ForeignKey(DiscordServer, on_delete=models.CASCADE)
    parent = models.ForeignKey(DiscordUser, on_delete=models.CASCADE)

class DiscordChannel(models.Model):
    """Channel model"""
    name = models.CharField(max_length=255)
    server = models.ForeignKey(DiscordServer, on_delete=models.CASCADE)


class YTSong(models.Model):
    """Youtube song model"""
    title = models.CharField(max_length=255)
    url = models.CharField(max_length=255)
    duration = models.CharField(max_length=255)
    local_path = models.CharField(max_length=512)

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def times_played(self):
        """Return the number of times the song has been played"""
        return self.play_events.count()

    @classmethod
    def last_played(cls):
        """Return the last played song"""
        return cls.play_events.order_by('date').last()

class PlayEvent(models.Model):
    """Play event model"""
    user = models.ForeignKey(DiscordUser, on_delete=models.CASCADE)
    song = models.ForeignKey(YTSong, on_delete=models.CASCADE, related_name='play_events')

    date = models.DateTimeField(auto_now_add=True)


class Playlist(models.Model):
    """Playlist model"""
    name = models.CharField(max_length=255)
    songs = models.ManyToManyField(YTSong)

    created_at = models.DateTimeField(auto_now_add=True)
