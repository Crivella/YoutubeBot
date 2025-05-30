"""Music commands for the bot"""
import logging
import os

import discord
from discord import app_commands
from django.db.models import Q

from ... import models as m
from ...models import filters as flt
from ...models.quiz_hl import allowed_params, object_type_map
from ..utils import safe_defer, safe_response
from ..views.utils import elide

logger = logging.getLogger('bot')

MAX_AUTO_COMPLETE = int(os.getenv('BOT_MAX_AUTO_COMPLETE', 20))

# TODO: need to add proper invalidation before using this
#  probably based on django signals on when playlists are updated
# server_playlist_cache = {}

NONE_STR = '__NO__NE__'

class PlaylistTransformer(app_commands.Transformer):
    def __init__(self, *args, enforce_user: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.enforce_user = enforce_user
    async def transform(self, ctx: discord.Interaction, argument: str):
        if argument is None or argument == NONE_STR:
            return
        server = await m.DiscordServer.from_discord_guild(ctx.guild)
        user = await m.DiscordUser.from_discord_user(ctx.user)
        try:
            if self.enforce_user:
                playlist = await m.Playlist.objects.aget(server=server, owner=user, name=argument)
            else:
                playlist = await m.Playlist.objects.aget(server=server, name=argument)
        except m.Playlist.DoesNotExist:
            await safe_response(ctx, f'Playlist `{argument}` not found', ephemeral=True)
            raise ValueError(f'Playlist `{argument}` not found')
        return playlist

    async def autocomplete(self, ctx: discord.Interaction, current: str):
        server = await m.DiscordServer.from_discord_guild(ctx.guild)
        q = m.Playlist.objects
        if self.enforce_user:
            user = await m.DiscordUser.from_discord_user(ctx.user)
            q = q.filter(server=server, owner=user, name__startswith=current)
        else:
            q = q.filter(server=server, name__startswith=current)
        cnt = await q.acount()
        if cnt > MAX_AUTO_COMPLETE:
            return [app_commands.Choice(name=f'{cnt} playlists found', value=NONE_STR)]
        playlists = [p async for p in q.all()]
        return [app_commands.Choice(name=p.name, value=p.name) for p in playlists]

server_playlist_cache: dict[int, list[m.YTSong]] = {}
class SongTransformer(app_commands.Transformer):
    def __init__(
            self, *args,
            allow_new: bool = False,
            nullable: bool = False,
            from_server_playlist: bool = False,
            **kwargs
        ):
        super().__init__(*args, **kwargs)
        self.song_map = {}
        self.allow_new = allow_new
        self.nullable = nullable
        self.from_server_playlist = from_server_playlist

    async def transform(self, ctx: discord.Interaction, argument: str):
        if argument is None or argument == NONE_STR:
            if self.nullable:
                return
            raise ValueError(f'Song cannot be null')
        song = self.song_map.get(argument, argument)
        if isinstance(song, str):
            if not self.allow_new:
                await safe_response(ctx, f'Song `{argument}` not found', ephemeral=True)
                raise ValueError(f'Song `{argument}` not found')
            await safe_response(ctx, f'Searching for {argument}', ephemeral=True, delete_after=240)
            try:
                song = await m.YTSong.from_search_string(argument)
            except Exception as e:
                await safe_response(ctx, f'Error searching for {argument}: {e}', ephemeral=True)
                raise ValueError(f'Error searching for {argument}: {e}')
        return song

    async def autocomplete(self, ctx: discord.Interaction, current: str):
        await safe_defer(ctx)

        if self.from_server_playlist:
            songs = server_playlist_cache.get(ctx.guild.id, [])
            songs = [s for s in songs if current.lower() in s.title.lower()]
            if len(songs) > MAX_AUTO_COMPLETE:
                return [app_commands.Choice(name=f'{len(songs)} songs found', value=NONE_STR)]
        else:
            q = m.YTSong.objects
            q = flt.song_annotate_title(q)
            q = q.filter(title__icontains=current)
            cnt = await q.acount()
            if cnt > MAX_AUTO_COMPLETE:
                return [app_commands.Choice(name=f'{cnt} songs found', value=NONE_STR)]
            songs = [s async for s in q.all()]

        self.song_map = {s.youtube_id: s for s in songs}
        return [
            app_commands.Choice(
                name=f'[{s.duration}] {elide(s.title, 50)}',
                value=s.youtube_id
            )
            for s in songs
        ]

    @staticmethod
    def register_server_playlist(server_id: int, songs: list[m.YTSong]):
        server_playlist_cache[server_id] = songs.copy()

    @staticmethod
    def remove_server_playlist(server_id: int):
        server_playlist_cache.pop(server_id, None)

class SongFilterTransformer(app_commands.Transformer):
    async def transform(self, ctx: discord.Interaction, argument: str):
        return argument

    async def autocomplete(self, ctx: discord.Interaction, current: str):
        return [
            app_commands.Choice(name=flt.song_order_descr[k], value=k) for k in flt.song_order_map.keys()
            if k.startswith(current)
        ]

class ObjectTypeTransformer(app_commands.Transformer):
    async def transform(self, ctx: discord.Interaction, argument: str):
        return argument

    async def autocomplete(self, ctx: discord.Interaction, current: str):
        return [
            app_commands.Choice(name=el, value=el) for el in object_type_map.keys()
            if el.startswith(current.upper())
        ]

class ObjectParamTransformer(app_commands.Transformer):
    async def transform(self, ctx: discord.Interaction, argument: str):
        return argument

    async def autocomplete(self, ctx: discord.Interaction, current: str):
        allowed = set()
        for v in allowed_params.values():
            allowed |= set(v)
        return [
            app_commands.Choice(name=el, value=el) for el in allowed
            if el.startswith(current.upper())
        ]

class AnimeTransformer(app_commands.Transformer):
    def __init__(
            self, *args,
            allow_new: bool = False,
            nullable: bool = False,
            # from_server_playlist: bool = False,
            **kwargs
        ):
        super().__init__(*args, **kwargs)
        self.anime_map = {}
        self.allow_new = allow_new
        self.nullable = nullable
        # self.from_server_playlist = from_server_playlist

    async def transform(self, ctx: discord.Interaction, argument: str):
        if argument is None or argument == NONE_STR:
            if self.nullable:
                return
            raise ValueError(f'Song cannot be null')
        anime = self.anime_map.get(argument, argument)
        if isinstance(anime, str):
            if not self.allow_new:
                await safe_response(ctx, f'Anime `{argument}` not found', ephemeral=True)
                raise ValueError(f'Anime `{argument}` not found')
            await safe_response(ctx, f'Searching for {argument}', ephemeral=True, delete_after=240)
            try:
                anime = await m.AnimeObj.from_string(argument)
            except Exception as e:
                await safe_response(ctx, f'Error searching for {argument}: {e}', ephemeral=True)
                raise ValueError(f'Error searching for {argument}: {e}')
        return anime

    async def autocomplete(self, ctx: discord.Interaction, current: str):
        await safe_defer(ctx)

        q = m.AnimeObj.objects
        q = q.filter(
            Q(title__icontains=current) |
            Q(title_english__icontains=current)
        )
        cnt = await q.acount()
        if cnt > MAX_AUTO_COMPLETE:
            return [app_commands.Choice(name=f'{cnt} anime found', value=NONE_STR)]
        anime = [a async for a in q.all()]

        self.anime_map = {str(a.mal_id): a for a in anime}
        return [
            app_commands.Choice(
                name=f'{elide(a.title, 50)}',
                value=str(a.mal_id)
            )
            for a in anime
        ]

# class UserListTransformer(app_commands.Transformer):
#     async def transform(self, ctx: discord.Interaction, argument: str) -> list[m.DiscordUser]:
#         print('transform', argument)
#         argument = argument.replace(' ', '')
#         names = argument.split(',')
#         users = ctx.user.voice.channel.members
#         res = [u for u in users if u.display_name in names]
#         return res

#     async def autocomplete(self, ctx: discord.Interaction, current: str):
#         if len(current) and not current.endswith(','):
#             return []
#         users = ctx.user.voice.channel.members
#         current = current.replace(' ', '')
#         prev = current.split(',')[:-1]
#         last = current.split(',')[-1]
#         return [
#             app_commands.Choice(
#                 name=', '.join(prev + [u.display_name]),
#                 value=','.join(prev + [u.display_name])
#             )
#             for u in users
#             if u.display_name.startswith(last) and u.display_name not in prev
#         ]

class IntRangeTransformer(app_commands.Transformer):
    def __init__(
            self, *args,
            min: int = None, max: int = None,
            nullable: bool = False,
            **kwargs
        ):
        super().__init__(*args, **kwargs)
        self.min_ = min
        self.max_ = max
        self.nullable = nullable
    async def transform(self, ctx: discord.Interaction, argument: int | str):
        if argument is None:
            if self.nullable:
                return None
            await safe_response(ctx, f'Value cannot be null', ephemeral=True)
            raise ValueError(f'Value cannot be null')
        try:
            res = int(argument)
        except ValueError:
            await safe_response(ctx, f'Invalid integer: {argument}', ephemeral=True)
            raise ValueError(f'Invalid integer: {argument}')

        if self.min_ is not None and res < self.min_:
            await safe_response(ctx, f'Value must be greater than {self.min_}', ephemeral=True)
            raise ValueError(f'Value must be >= than {self.min_}')
        if self.max_ is not None and res > self.max_:
            await safe_response(ctx, f'Value must be <= than {self.max_}', ephemeral=True)
            raise ValueError(f'Value must be less than {self.max_}')

        return res
