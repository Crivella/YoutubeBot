"""Events models"""

from django.db import models


class PlayEvent(models.Model):
    """Play event model"""
    user = models.ForeignKey('DiscordUser', on_delete=models.CASCADE)
    song = models.ForeignKey('YTSong', on_delete=models.CASCADE)
    server = models.ForeignKey('DiscordServer', on_delete=models.CASCADE)

    date = models.DateTimeField(auto_now_add=True)

class GuessSongEvent(models.Model):
    """Guess song event model"""
    real_song = models.ForeignKey('YTSong', on_delete=models.CASCADE, related_name='+')
    guessed_song = models.ForeignKey('YTSong', on_delete=models.CASCADE, related_name='+')

    start = models.IntegerField(null=True)
    end = models.IntegerField(null=True)
    num_choices = models.IntegerField(null=True)

    user = models.ForeignKey('DiscordUser', on_delete=models.CASCADE, null=True, default=None, related_name='song_guesses')
    date = models.DateTimeField(auto_now_add=True)

    def __bool__(self):
        return self.real_song_id == self.guessed_song_id

class AddedSongEvent(models.Model):
    """Added song event model"""
    song = models.ForeignKey('YTSong', on_delete=models.CASCADE)
    server = models.ForeignKey('DiscordServer', on_delete=models.CASCADE)

    user = models.ForeignKey('DiscordUser', on_delete=models.CASCADE)
    date = models.DateTimeField(auto_now_add=True)
