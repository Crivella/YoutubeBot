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

    # async def get_embed(self) -> discord.Embed:
    #     """Generate the embed"""
    #     creator = await DiscordUser.objects.aget(id=self.creator_id)
    #     playlist = await Playlist.objects.aget(id=self.playlist_id) if self.playlist_id else None
    #     score = await self.get_score()
    #     users = [user async for user in self.players.all()]
    #     users.sort(key=lambda _: score.get(_.id, 0), reverse=True)

    #     fmt = '%Y-%m-%d %H:%M:%S'
    #     start = self.date_start.strftime(fmt)
    #     end = self.date_end.strftime(fmt) if self.date_end else 'Unfinished'
    #     desc = []
    #     desc.append(f'CREATOR: {creator.username}')
    #     desc.append(f'START: {start} - END: {end}')
    #     res = discord.Embed(
    #         title=f'QuizSong',
    #         description='\n'.join(desc),
    #         color=discord.Color.blurple()
    #     )

    #     res.add_field(
    #         name='Players',
    #         value='\n'.join(f'{_.username} ({score[_.id]})' for _ in users)
    #     )
    #     params_msg = []
    #     params_msg.append(f'- Playlist={playlist.name if playlist else "None"} (tot={self.total_choices})')
    #     params_msg.append(f'- num_songs={self.num_songs}')
    #     params_msg.append(f'- num_choices={self.num_choices}')
    #     params_msg.append(f'- segment_mode={self.segment_mode}')
    #     params_msg.append(f'- segment_length={self.segment_length}')
    #     params_msg.append(f'- audio_filter="{self.audio_filter}"')
    #     params_msg.append(f'- multiple_choice={self.multiple_choice}')
    #     params_msg.append(f'- show_thumbnail={self.show_thumbnail} (blur={self.thumbnail_blur})')
    #     res.add_field(name='Parameters', value='\n'.join(params_msg))
    #     return res

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
