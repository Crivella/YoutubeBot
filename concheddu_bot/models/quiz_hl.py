"""Quiz models on songs"""
import discord
from django.db import models
from django.utils import timezone

from .anime import AnimeCharacter, AnimeObj
from .discord import DiscordUser
from .events import GuessHighLowEvent

object_type_map = {
    'anime': AnimeObj,
    'anime_character': AnimeCharacter,
}
object_type_map_inv = {v: k for k, v in object_type_map.items()}

allowed_params = {
    'anime': ['favorites', 'score'],
    'anime_character': ['favorites'],
}

class QuizHighLow(models.Model):
    """QuizHighLow song model"""
    object_type = models.CharField(
        max_length=32, choices=[
            ('anime', 'Anime'),
            ('anime_character', 'Anime Character'),
        ]
    )
    object_param = models.CharField(max_length=64, null=True, blank=True)
    num_objects = models.IntegerField(default=0)
    max_top = models.IntegerField(default=0)

    server = models.ForeignKey('DiscordServer', on_delete=models.CASCADE)
    player = models.ForeignKey('DiscordUser', on_delete=models.CASCADE, related_name='quiz_highlow')

    object_choice_ids = models.JSONField()

    date_start = models.DateTimeField(auto_now_add=True)
    date_end = models.DateTimeField(null=True)

    async def finish(self):
        """Finish the quiz"""
        self.date_end = timezone.now()
        await self.asave()

    async def guess(
            self, id1: int, id2: int, guess_direction: int,
            user: 'DiscordUser'
        ) -> bool:
        """Guess a song in the high-low quiz

        Args:
            id1 (int): ID of the first object with known favorite number
            id2 (int): ID of the second object with known favorite number
            guess_direction (int): Guess the relation of the 2nd object to the first one.
                1 for higher, -1 for lower
            user (DiscordUser): _description_

        Returns:
            bool: _description_
        """
        object_cls = object_type_map[self.object_type]
        obj1 = await object_cls.objects.aget(id=id1)
        obj2 = await object_cls.objects.aget(id=id2)

        v1 = getattr(obj1, self.object_param)
        v2 = getattr(obj2, self.object_param)
        if v1 > v2:
            correct = guess_direction < 0
        elif v1 < v2:
            correct = guess_direction > 0
        else:
            correct = True

        await GuessHighLowEvent.objects.acreate(
            quiz=self,
            item1_id=id1,
            item2_id=id2,
            direction=guess_direction,
            user=user
        )

        return correct
