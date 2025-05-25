"""Events models"""

from django.db import models


class PlayEvent(models.Model):
    """Play event model"""
    user = models.ForeignKey('DiscordUser', on_delete=models.CASCADE)
    song = models.ForeignKey('YTSong', on_delete=models.CASCADE)
    server = models.ForeignKey('DiscordServer', on_delete=models.CASCADE)

    start = models.IntegerField(null=True)
    end = models.IntegerField(null=True)
    audio_filter = models.CharField(max_length=512, null=True)

    quiz = models.ForeignKey(
        'QuizSong', on_delete=models.DO_NOTHING,  # Do not delete events if quiz is deleted
        null=True,  # QuizSong is nullable to accommodate previous plays without quiz
        default=None,
        related_name='plays'
    )

    date = models.DateTimeField(auto_now_add=True)

class GuessSongEvent(models.Model):
    """Guess song event model"""
    real_song = models.ForeignKey('YTSong', on_delete=models.CASCADE, related_name='+')
    guessed_song = models.ForeignKey(
        'YTSong', on_delete=models.CASCADE, related_name='+',
        # Use non to denote a skip (go on without guessing)
        null=True
        )

    # Guesses on songs are done on segments
    start = models.IntegerField(null=True)
    end = models.IntegerField(null=True)
    # Value of choices in a multiple choice quiz or all songs in a free quiz
    num_choices = models.IntegerField(null=True)

    # Time to answer in seconds
    # - from the first time play was called or
    # - from the first time the question was generated otherwise
    time_to_answer = models.FloatField(null=True)

    # The thumbnail used for the song
    thumbnail = models.ForeignKey('ImageObj', on_delete=models.SET_NULL, null=True)
    blur = models.IntegerField(default=0)

    user = models.ForeignKey(
        'DiscordUser', on_delete=models.CASCADE,
        null=True,  # Allow null to accomodate previous guesses without user
        default=None,
        related_name='song_guesses'
        )
    date = models.DateTimeField(auto_now_add=True)

    # The quiz this guess is part of

    quiz = models.ForeignKey(
        'QuizSong', on_delete=models.CASCADE,
        null=True,  # QuizSong is nullable to accomodate previous guesses without quiz
        default=None,
        related_name='guesses'
        )
    # The number of time the song was played before the guess
    num_plays = models.IntegerField(default=0)

    def __bool__(self):
        return self.real_song_id == self.guessed_song_id

class AddedSongEvent(models.Model):
    """Added song event model"""
    song = models.ForeignKey('YTSong', on_delete=models.CASCADE)
    server = models.ForeignKey('DiscordServer', on_delete=models.CASCADE)

    user = models.ForeignKey('DiscordUser', on_delete=models.CASCADE)
    date = models.DateTimeField(auto_now_add=True)

class CallCommandEvent(models.Model):
    """Call command event model"""
    user = models.ForeignKey('DiscordUser', on_delete=models.CASCADE)
    server = models.ForeignKey('DiscordServer', on_delete=models.CASCADE)
    command = models.CharField(max_length=512)

    args = models.JSONField()
    kwargs = models.JSONField()

    error = models.TextField(null=True)

    date = models.DateTimeField(auto_now_add=True)
