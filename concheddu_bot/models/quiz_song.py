"""Quiz models on songs"""
from datetime import datetime

from django.db import models
from django.utils import timezone

from .events import GuessSongEvent
from .yt_song import YTSong


class QuizSong(models.Model):
    """Quiz song model"""
    num_songs = models.IntegerField()
    num_choices = models.IntegerField()
    total_songs = models.IntegerField()
    total_choices = models.IntegerField()
    segment_mode = models.CharField(max_length=32)
    segment_length = models.IntegerField()
    audio_filter = models.CharField(max_length=512, null=True)

    server = models.ForeignKey('DiscordServer', on_delete=models.CASCADE)
    creator = models.ForeignKey('DiscordUser', on_delete=models.CASCADE)
    players = models.ManyToManyField('DiscordUser', related_name='quizzes')
    playlist = models.ForeignKey('Playlist', on_delete=models.SET_NULL, null=True)

    song_choice_ids = models.JSONField()

    date_start = models.DateTimeField(auto_now_add=True)
    date_end = models.DateTimeField(null=True)

    async def finish(self):
        """Finish the quiz"""
        self.date_end = datetime.now()
        await self.asave()

    async def guess(
            self, song_id: int, answer_id: int, user: 'DiscordUser',
            start: int, end: int, num_choices: int,
            num_plays: int = 0,
            time: int = None
        ) -> bool:
        """Guess a song"""
        song = await YTSong.objects.aget(youtube_id=song_id)
        answer = await YTSong.objects.aget(youtube_id=answer_id)
        res = song_id == answer_id
        song.times_answered += 1
        song.times_guessed += res
        await song.asave()
        await GuessSongEvent.objects.acreate(
            quiz=self,
            real_song=song,
            guessed_song=answer,
            user=user,
            start=start,
            end=end,
            num_choices=num_choices,
            num_plays=num_plays,
            time_to_answer=time
        )
        return res

    async def get_score(self) -> dict[int, int]:
        """Get the score"""
        res = {}
        async for user in self.players.all():
            res[user.id] = await self.guesses.filter(
                user=user, real_song=models.F('guessed_song')
            ).acount()
        return res
