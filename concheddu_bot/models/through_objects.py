"""Many-to-many through models"""

from django.db import models


class PlaylistThrough(models.Model):
    """Playlist through model"""
    playlist = models.ForeignKey('Playlist', on_delete=models.CASCADE)
    song = models.ForeignKey('YTSong', on_delete=models.CASCADE)

    order = models.IntegerField()

    added_date = models.DateTimeField(auto_now_add=True)
