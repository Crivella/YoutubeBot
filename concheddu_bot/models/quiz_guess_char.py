"""Quiz models on songs"""
from django.db import models
from django.utils import timezone

from .anime import AnimeCharacter, AnimeCharacterThrough, AnimeObj
from .discord import DiscordUser
from .events import GuessAnimeCharacterEvent

allowed_image_types = ['thumbnail', 'eyes']


class QuizAnimeCharacter(models.Model):
    """QuizHighLow song model"""
    num_objects = models.IntegerField(default=0)
    max_top = models.IntegerField(default=0)
    max_choices = models.IntegerField(default=0)
    max_anime_choices = models.IntegerField(default=0)
    min_favorites = models.IntegerField(default=-1)
    max_favorites = models.IntegerField(default=-1)

    image_type = models.CharField(
        max_length=64,
        default='thumbnail',
        help_text='Type of image to use for the characters (thumbnail, eyes, etc.)'
    )

    collections = models.ManyToManyField(
        'AnimeCollection',
        related_name='quiz_anime_characters',
        blank=True,
        help_text='Collections to filter the characters from'
    )

    server = models.ForeignKey('DiscordServer', on_delete=models.CASCADE)
    creator = models.ForeignKey('DiscordUser', on_delete=models.CASCADE)
    players = models.ManyToManyField('DiscordUser', related_name='quiz_anime_characters')

    object_choice_ids = models.JSONField()

    date_start = models.DateTimeField(auto_now_add=True)
    date_end = models.DateTimeField(null=True)

    async def finish(self):
        """Finish the quiz"""
        self.date_end = timezone.now()
        await self.asave()

    async def guess(
            self,
            real: 'AnimeCharacter',
            user: 'DiscordUser',
            guessed_char: 'AnimeCharacter' = None,
            guessed_anime: 'AnimeObj' = None
        ) -> tuple[bool, bool]:
        """Guess a song in the high-low quiz

        Args:
            real (AnimeCharacter): The real character to guess
            user (DiscordUser): The user who made the guess
            chara_id (AnimeCharacter | None): The guessed character ID, if any
            anime_id (AnimeObj | None): The guessed anime ID, if any

        Returns:
            bool: _description_
        """

        res1 = real.id == (guessed_char.id if guessed_char else None)
        res2 = False
        if guessed_anime is not None:
            q = AnimeCharacterThrough.objects
            q = q.filter(anime=guessed_anime, character=real)
            res2 = await q.aexists()


        await GuessAnimeCharacterEvent.objects.acreate(
            quiz=self,
            real_character=real,
            guessed_character=guessed_char,
            guessed_anime=guessed_anime,
            user=user
        )

        return res1, res2
