"""Quiz models on songs"""
import discord
from django.db import models
from django.utils import timezone

from .discord import DiscordUser
from .events import GuessSongEvent
from .playlist import Playlist
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

    multple_choice = models.BooleanField(default=True)

    date_start = models.DateTimeField(auto_now_add=True)
    date_end = models.DateTimeField(null=True)

    async def get_embed(self) -> discord.Embed:
        """Generate the embed"""
        creator = await DiscordUser.objects.aget(id=self.creator_id)
        playlist = await Playlist.objects.aget(id=self.playlist_id) if self.playlist_id else None
        score = await self.get_score()
        users = [user async for user in self.players.all()]
        users.sort(key=lambda _: score.get(_.id, 0), reverse=True)

        fmt = '%Y-%m-%d %H:%M:%S'
        start = self.date_start.strftime(fmt)
        end = self.date_end.strftime(fmt) if self.date_end else 'Unfinished'
        desc = []
        desc.append(f'CREATOR: {creator.username}')
        desc.append(f'START: {start} - END: {end}')
        res = discord.Embed(
            title=f'QuizSong',
            description='\n'.join(desc),
            color=discord.Color.blurple()
        )

        res.add_field(
            name='Players',
            value='\n'.join(f'{_.username} ({score[_.id]})' for _ in users)
        )
        params_msg = []
        params_msg.append(f'- Playlist={playlist.name if playlist else "None"} (tot={self.total_choices})')
        params_msg.append(f'- num_songs={self.num_songs}')
        params_msg.append(f'- num_choices={self.num_choices}')
        params_msg.append(f'- segment_mode={self.segment_mode}')
        params_msg.append(f'- segment_length={self.segment_length}')
        params_msg.append(f'- audio_filter="{self.audio_filter}"')
        res.add_field(name='Parameters', value='\n'.join(params_msg))
        return res

    async def finish(self):
        """Finish the quiz"""
        self.date_end = timezone.now()
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
