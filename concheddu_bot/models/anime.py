import asyncio
import datetime
import logging
import re

import discord
from django.db import models
from jikanpy import AioJikan
from jikanpy.exceptions import JikanException

from .image import ImageObj

logger = logging.getLogger('bot')

mal_rgx = re.compile(r'https?://(?:www\.)?myanimelist\.net/anime/(\d+)')

jikan_key_map = [
    # ('mal_id', 'mal_id'),
    ('title', 'title'),
    ('title_english', 'title_english'),
    ('title_japanese', 'title_japanese'),
    ('synopsis', 'description'),
    ('episodes', 'num_episodes'),
    # ('aired', 'aired_from'),  # This will be a dict, we will handle it later
    ('type', 'type'),
    ('source', 'source'),
    ('score', 'score'),
    ('scored_by', 'scored_by'),
    ('rank', 'rank'),
    ('popularity', 'popularity'),
    ('members', 'members'),
    ('favorites', 'favorites'),
]

API_DELAY = 1.5  # seconds to wait between API calls to avoid hitting rate limits

def get_image_url(data: dict) -> str:
    """Get the image URL from the data dictionary"""
    for formats in ['webp', 'jpg', 'png']:
        if formats in data:
            for size in ['large_image_url', 'image_url', 'small_image_url']:
                if size in data[formats]:
                    return data[formats][size]
    return None

class AnimeStudio(models.Model):
    """Anime Studio model"""
    name = models.CharField(max_length=512, unique=True, help_text='Name of the anime studio')
    mal_id = models.IntegerField(unique=True, null=True, blank=True, help_text='MyAnimeList ID of the studio')

    def __str__(self):
        return self.name

class AnimeGenre(models.Model):
    """Anime Genre model"""
    name = models.CharField(max_length=64, unique=True, help_text='Name of the anime genre')
    mal_id = models.IntegerField(unique=True, null=True, blank=True, help_text='MyAnimeList ID of the genre')

    def __str__(self):
        return self.name

class AnimeObj(models.Model):
    """Anime model"""
    mal_id = models.IntegerField(unique=True)

    title = models.CharField(max_length=512, help_text='Title of the anime')
    title_english = models.CharField(max_length=512, null=True, blank=True)
    title_japanese = models.CharField(max_length=512, null=True, blank=True)

    description = models.TextField(null=True, blank=True)

    thumbnail = models.ForeignKey(
        ImageObj, on_delete=models.SET_NULL, null=True, blank=True, related_name='anime_thumbnails'
    )
    places = models.ManyToManyField(
        'ImageObj', blank=True, related_name='anime_places',
        help_text='Images of places from the anime'
    )

    type = models.CharField(
        max_length=64, choices=[
            ('tv', 'TV'),
            ('movie', 'Movie'),
            ('ova', 'OVA'),
            ('ona', 'ONA'),
            ('special', 'Special'),
            ('music', 'Music')
        ], default='tv',
        help_text='Type of the anime'
    )
    source = models.CharField(
        max_length=64, choices=[
            ('original', 'Original'),
            ('manga', 'Manga'),
            ('light_novel', 'Light Novel'),
            ('visual_novel', 'Visual Novel'),
            ('video_game', 'Video Game'),
            ('other', 'Other')
        ], default='original',
        help_text='Source material of the anime'
    )

    num_episodes = models.IntegerField(
        null=True, blank=True, help_text='Number of episodes in the anime'
    )
    aired_from = models.DateField(null=True, blank=True, help_text='Start date of airing')
    aired_to = models.DateField(null=True, blank=True, help_text='End date of airing')

    date = models.DateTimeField(auto_now_add=True, help_text='Creation date of the anime entry')

    score = models.FloatField(
        null=True, blank=True, help_text='Average score from MyAnimeList'
    )
    scored_by = models.IntegerField(
        null=True, blank=True, help_text='Number of users who scored this anime on MyAnimeList'
    )
    rank = models.IntegerField(
        null=True, blank=True, help_text='Rank of the anime on MyAnimeList'
    )
    popularity = models.IntegerField(
        null=True, blank=True, help_text='Popularity score on MyAnimeList'
    )
    members = models.IntegerField(
        null=True, blank=True, help_text='Number of members on MyAnimeList'
    )
    favorites = models.IntegerField(
        null=True, blank=True, help_text='Number of favorites on MyAnimeList'
    )

    studios = models.ManyToManyField(
        AnimeStudio, blank=True, related_name='animes',
        help_text='Studios that produced the anime'
    )

    genres = models.ManyToManyField(
        AnimeGenre, blank=True, related_name='animes',
        help_text='Genres of the anime'
    )

    @classmethod
    async def from_top(cls, start: int = 0, num: int = 10, force: bool = False) -> list['AnimeObj']:
        """Fetch top anime from MyAnimeList"""
        page = start // 25 + 1 # MyAnimeList pages are 25 items each
        animes = []
        while num > 0:
            logging.info(f'Fetching top anime page {page} with {num} entries remaining')
            async with AioJikan() as jikan:
                try:
                    res_data = await jikan.top(type='anime', page=page)
                except JikanException as e:
                    logger.error(f'Failed to fetch top anime: {e}')
                    break

            top_data = res_data.get('data', [])
            top_data = top_data[:num]  # Limit to the requested number
            num -= len(top_data)
            for anime_data in top_data:
                mal_id = anime_data.get('mal_id')
                if not mal_id:
                    logger.warning("Anime data missing 'mal_id', skipping")
                    continue
                animes.append(await cls.from_jikan_data(anime_data, force=force))

            pagination_data = res_data.get('pagination', {})
            has_next = pagination_data.get('has_next_page', False)
            if not has_next:
                logger.warning('No more pages available in top anime list')
                break
            page += 1
            await asyncio.sleep(API_DELAY)

        logger.info(f'Fetched {len(animes)} anime entries from MyAnimeList')
        return animes

    async def get_str(self) -> str:
        """Get a string representation of the anime"""
        return f'{self.title}'

    @classmethod
    async def from_url(cls, url: str):
        """Create an Anime instance from a URL"""
        # match = re.match(r'https?://(?:www\.)?myanimelist\.net/anime/(\d+)', url)
        match = cls.mal_rgx.match(url)
        if not match:
            raise ValueError('Invalid MAL URL')

        mal_id = match.group(1)
        if not mal_id.isdigit():
            raise ValueError('MAL ID must be a number')

        mal_id = int(mal_id)

        return await cls.from_id(mal_id)

    async def fetch_characters(self):
        """Fetch characters for this anime"""
        async with AioJikan() as jikan:
            try:
                characters_data = await jikan.anime(self.mal_id, extension='characters')
            except JikanException as e:
                logger.error(f'Failed to fetch characters for anime ID {self.mal_id}: {e}')
                return

        characters_data = characters_data['data']

        for char_data in characters_data:
            await AnimeCharacter.from_jikan_anime_data(char_data, self)

    def from_jikan_data_get_aired(self, data: dict):
        """Extract aired_from date from Jikan data"""
        aired_from = data.get('aired', {}).get('from')
        if aired_from:
            dt = datetime.datetime.fromisoformat(aired_from.replace('Z', '+00:00'))
            self.aired_from = dt.date()
        aired_to = data.get('aired', {}).get('to')
        if aired_to:
            dt = datetime.datetime.fromisoformat(aired_to.replace('Z', '+00:00'))
            self.aired_to = dt.date()

    def from_jikan_data_get_genres(self, data: dict):
        """Extract genres from Jikan data"""
        genres_data = data.get('genres', [])
        for genre in genres_data:
            genre_mal_id = genre.get('mal_id')
            genre_name = genre.get('name').capitalize()

            genre_obj, _ = AnimeGenre.objects.get_or_create(
                mal_id=genre_mal_id,
                defaults={'name': genre_name}
            )
            self.genres.add(genre_obj)

    def from_jikan_data_get_studios(self, data: dict):
        """Extract studios from Jikan data"""
        studios_data = data.get('studios', [])
        for studio in studios_data:
            studio_mal_id = studio.get('mal_id')
            studio_name = studio.get('name').capitalize()

            studio_obj, _ = AnimeStudio.objects.get_or_create(
                mal_id=studio_mal_id,
                defaults={'name': studio_name}
            )
            self.studios.add(studio_obj)

    @staticmethod
    async def get_all_types() -> list[str]:
        """Get all unique types of anime from the database"""
        types = await AnimeObj.objects.values_list('type', flat=True).distinct()
        return list(types)

    @classmethod
    async def from_jikan_data(cls, data: dict, force: bool = False) -> 'AnimeObj':
        """Create an Anime instance from Jikan data"""
        anime_id = data.get('mal_id')

        dct= {}
        for key, new_key in jikan_key_map:
            if key in data:
                dct[new_key] = data[key]
            else:
                dct[new_key] = None

        new, created = await cls.objects.aupdate_or_create(mal_id=anime_id, defaults=dct)
        logger.debug(f'{"Created new" if created else "Updated existing"} anime entry: {new.title} (ID: {new.mal_id})')

        thumbmail_url = get_image_url(data.get('images', {}))
        if thumbmail_url is not None and (new.thumbnail_id is None or force):
            new.thumbnail = await ImageObj.from_url(thumbmail_url)
            await new.asave()

        new.from_jikan_data_get_aired(data)
        new.from_jikan_data_get_studios(data)
        new.from_jikan_data_get_genres(data)

        if created or force:
            await new.fetch_characters()
            await asyncio.sleep(API_DELAY)  # When used to fecth anime sequentially, avoid hitting Jikan API too fast

        return new

    @classmethod
    async def from_id(cls, anime_id: int):
        """Create an Anime instance from a MAL ID"""
        if not isinstance(anime_id, int):
            raise ValueError('MAL ID must be an integer')

        try:
            new = await cls.objects.aget(mal_id=anime_id)
        except cls.DoesNotExist:
            logger.info(f'Anime with ID {anime_id} not found in database, fetching from Jikan')
        else:
            logger.info(f'Anime with ID {anime_id} found in database: {new}')
            return new

        async with AioJikan() as jikan:
            try:
                anime_data = await jikan.anime(anime_id)
            except JikanException as e:
                logger.error(f'Failed to fetch anime data for ID {anime_id}: {e}')
                raise ValueError(f'Anime with ID {anime_id} not found')
            await asyncio.sleep(API_DELAY)  # Avoid hitting Jikan API too fast
        logger.debug(f'Fetched anime data for ID {anime_id}: {anime_data}')

        anime_data = anime_data['data']

        return await cls.from_jikan_data(anime_data)

    @classmethod
    async def from_string(cls, anime_str: str):
        """Create an Anime instance from a string (title or URL)"""
        if anime_str.isdigit():
            return await cls.from_id(int(anime_str))
        elif cls.mal_rgx.match(anime_str):
            return await cls.from_url(anime_str)
        else:
            # Assume it's a title
            # Here you would typically search for the anime by title in an API
            raise NotImplementedError('Searching by title is not implemented yet')

    async def get_thumbnail(self) -> ImageObj | None:
        """Get the thumbnail image for this anime"""
        if self.thumbnail_id is None:
            return None
        try:
            return await ImageObj.objects.aget(id=self.thumbnail_id)
        except ImageObj.DoesNotExist:
            logger.warning(f'Thumbnail for anime {self.title} (ID: {self.mal_id}) not found')
            return None


    async def to_embed(self) -> tuple[discord.Embed, discord.File]:
        """Convert the Anime instance to a Discord embed"""
        embed = discord.Embed(
            title=self.title, description=self.description or 'No description available'
            )
        file = None

        thumbnail = await self.get_thumbnail()
        if thumbnail is not None:
            attach_name = f'anime_{self.mal_id}_thumbnail.webp'
            thumb_url = f'attachment://{attach_name}'
            file = discord.File(await thumbnail.get_image(), filename=attach_name)
            embed.set_thumbnail(url=thumb_url)

        embed.add_field(name='Episodes', value=str(self.num_episodes) if self.num_episodes else 'N/A')
        embed.add_field(name='Score', value=str(self.score) if self.score else 'N/A')
        embed.add_field(name='Rank', value=str(self.rank) if self.rank else 'N/A')
        embed.add_field(name='Popularity', value=str(self.popularity) if self.popularity else 'N/A')
        embed.add_field(name='Members', value=str(self.members) if self.members else 'N/A')
        embed.add_field(name='Favorites', value=str(self.favorites) if self.favorites else 'N/A')

        if self.aired_from:
            embed.add_field(name='Aired From', value=self.aired_from.strftime('%Y-%m-%d'))
        if self.aired_to:
            embed.add_field(name='Aired To', value=self.aired_to.strftime('%Y-%m-%d'))

        studios = ', '.join([studio.name async for studio in self.studios.all()]) or 'Unknown'
        genres = ', '.join([genre.name async for genre in self.genres.all()]) or 'Unknown'

        embed.add_field(name='Studios', value=studios)
        embed.add_field(name='Genres', value=genres)

        characters = await self.get_characters(top=5)
        char_lst = []
        for char in characters:
            char_lst.append(f'- {char.name} ({char.role.capitalize()}) [{char.favorites} favorites]')

        embed.add_field(
            name='Characters',
            value='\n'.join(char_lst) if char_lst else 'No characters found',
            inline=False
        )

        embed.set_footer(text=f'MAL ID: {self.mal_id}')

        return embed, file

    async def get_characters(self, top: int = 10) -> list['AnimeCharacter']:
        """Get characters from this anime"""
        q = self.characters.all()
        q = q.order_by('-favorites')[:top]
        return [char async for char in q]

class Language(models.Model):
    """Language model"""
    name = models.CharField(max_length=64, unique=True)

    def __str__(self):
        return self.name


class VoiceActor(models.Model):
    """Voice Actor model"""
    name = models.CharField(max_length=512)
    mal_id = models.IntegerField(unique=True, null=True, blank=True)

    thumbnail = models.ForeignKey(
        ImageObj, on_delete=models.SET_NULL, null=True, blank=True, related_name='voice_actor_thumbnails'
    )

    def __str__(self):
        return self.name

    @classmethod
    async def from_jikan_data(cls, data: dict, character: 'AnimeCharacter' = None):
        """Create a VoiceActor instance from Jikan data"""
        person_data = data.get('person', {})
        if not person_data:
            raise ValueError("Voice actor data must contain 'person' key")
        mal_id = person_data.get('mal_id')
        if not mal_id:
            raise ValueError("Voice actor data must contain 'mal_id'")
        name = person_data.get('name')
        if not name:
            raise ValueError("Voice actor data must contain 'name'")

        new, _ = await VoiceActor.objects.aupdate_or_create(
            mal_id=mal_id,
            defaults={'name': name}
        )

        if character is not None:
            language = data.get('language').capitalize()
            language_obj, _ = await Language.objects.aget_or_create(name=language)
            await VACthrough.objects.aget_or_create(
                voice_actor=new,
                character=character,
                language=language_obj
            )

        # thumbnail_url = get_image_url(person_data.get('images', {}))
        # if thumbnail_url:
        #     new.thumbnail = await ImageObj.from_url(thumbnail_url)
        #     await new.asave()

        return new


class VACthrough(models.Model):
    """Voice Actor Character Through model"""
    voice_actor = models.ForeignKey(VoiceActor, on_delete=models.CASCADE, related_name='throughs')
    character = models.ForeignKey('AnimeCharacter', on_delete=models.CASCADE, related_name='throughs')
    language = models.ForeignKey(Language, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.voice_actor.name} as {self.character.name} ({self.language.name if self.language else 'N/A'})"


class AnimeCharacter(models.Model):
    """Character model"""
    name = models.CharField(max_length=512)
    anime = models.ForeignKey(AnimeObj, on_delete=models.CASCADE, related_name='characters')
    description = models.TextField(null=True, blank=True)

    mal_id = models.IntegerField(unique=True, null=True, blank=True)
    role = models.CharField(
        max_length=64, choices=[
            ('main', 'Main Character'),
            ('supporting', 'Supporting Character'),
            # ('minor', 'Minor Character'),
            # ('background', 'Background Character')
        ], default='main',
        help_text='Role of the character in the anime'
    )
    favorites = models.IntegerField(default=0, help_text='Number of favorites on MyAnimeList')

    voice_actors = models.ManyToManyField(
        VoiceActor, through=VACthrough, related_name='characters', blank=True,
        help_text='Voice actors who voiced this character in different languages'
    )

    thumbnail = models.ForeignKey(
        ImageObj, on_delete=models.SET_NULL, null=True, blank=True, related_name='character_thumbnails'
    )
    eyes_img = models.ForeignKey(
        ImageObj, on_delete=models.SET_NULL, null=True, blank=True, related_name='character_eyes'
    )
    hair_img = models.ForeignKey(
        ImageObj, on_delete=models.SET_NULL, null=True, blank=True, related_name='character_hair'
    )
    body_img = models.ForeignKey(
        ImageObj, on_delete=models.SET_NULL, null=True, blank=True, related_name='character_body'
    )

    def __str__(self):
        return f'{self.name} ({self.anime.title})'

    @classmethod
    async def from_jikan_anime_data(cls, data: dict, anime: AnimeObj = None):
        """Create a Character instance from Jikan anime extension data"""
        cdata = data.get('character', {})
        if not cdata:
            raise ValueError("Character data must contain 'character' key")
        mal_id = cdata.get('mal_id')
        if not mal_id:
            raise ValueError("Character data must contain a 'mal_id'")
        name = cdata.get('name')
        if not name:
            raise ValueError("Character data must contain a 'name'")

        role = data.get('role', 'supporting')
        favorites = data.get('favorites', 0)

        defaults = {
            'name': name,
            'role': role,
            'favorites': favorites,
            'anime': anime
        }

        new, _ = await cls.objects.aupdate_or_create(
            mal_id=mal_id, defaults=defaults
        )
        thumbnail_url = get_image_url(cdata.get('images', {}))
        if thumbnail_url:
            new.thumbnail = await ImageObj.from_url(thumbnail_url)
            await new.asave()

        voice_actors_data = data.get('voice_actors', [])
        for va_data in voice_actors_data:
            try:
                await VoiceActor.from_jikan_data(va_data, character=new)
            except ValueError as e:
                logger.warning(f'Skipping voice actor data for character {new.name}: {e}')
                continue

        if anime is not None:
            new.anime = anime
            await new.asave()

        return new

    async def get_thumbnail(self) -> ImageObj | None:
        """Get the thumbnail image for this character"""
        if self.thumbnail_id is None:
            return None
        try:
            return await ImageObj.objects.aget(id=self.thumbnail_id)
        except ImageObj.DoesNotExist:
            logger.warning(f'Thumbnail for character {self.name} (ID: {self.mal_id}) not found')
            return None

    async def get_str(self):
        """Get a string representation of the character"""
        anime = await AnimeObj.objects.aget(id=self.anime_id)
        return f'{self.name} ({anime.title})'

    async def to_embed(self) -> tuple[discord.Embed, discord.File]:
        """Convert the Character instance to a Discord embed"""
        embed = discord.Embed(
            title=self.name,
            description=self.description or 'No description available',
            color=discord.Color.blurple()
        )

        file = None
        thumbnail = await self.get_thumbnail()
        if thumbnail is not None:
            attach_name = f'character_{self.mal_id}_thumbnail.webp'
            file = discord.File(await thumbnail.get_image(), filename=attach_name)
            embed.set_thumbnail(url=f'attachment://{attach_name}')

        embed.add_field(name='Role', value=self.role.capitalize(), inline=True)
        embed.add_field(name='Favorites', value=str(self.favorites), inline=True)

        if self.anime:
            embed.add_field(name='Anime', value=self.anime.title, inline=False)

        return embed, file

    # async def add_to_embed(self, embed: discord.Embed) -> discord.File:
    #     """Add character information to a Discord embed"""
    #     embed.add_field(name='Character', value=self.name, inline=False)
    #     embed.add_field(name='Role', value=self.role.capitalize(), inline=True)
    #     embed.add_field(name='Favorites', value=str(self.favorites), inline=True)

    #     if self.description:
    #         embed.add_field(name='Description', value=self.description, inline=False)

    #     if self.thumbnail_id:
    #         thumbnail = await ImageObj.objects.aget(id=self.thumbnail_id)
    #         attach_name = f'character_{self.mal_id}_thumbnail.webp'
    #         file = discord.File(await thumbnail.get_image(), filename=attach_name)
    #         embed.set_thumbnail(url=f'attachment://{attach_name}')
    #         return file

    #     return None
