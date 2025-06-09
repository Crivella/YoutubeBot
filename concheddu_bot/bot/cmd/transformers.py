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

object_server_cache: dict = {}

class GenericObjectTransformer(app_commands.Transformer):
    klass = None
    from_argument_function_name: str = None
    list_filters = []
    query_filters = []
    map_attribute = None
    descr_function_name = None

    def __init__(
            self, *args,
            allow_new: bool = False,
            nullable: bool = False,
            from_cache: bool = False,
            verbose: bool = True,
            **kwargs
        ):
        super().__init__(*args, **kwargs)
        self.object_map = {}
        self.allow_new = allow_new
        self.nullable = nullable
        self.from_cache = from_cache
        self.verbose = verbose

    async def transform(self, ctx: discord.Interaction, argument: str):
        if argument is None or argument == NONE_STR:
            if self.nullable:
                return
            raise ValueError(f'{self.klass.__name__} cannot be null')
        res = self.object_map.get(argument, argument)
        if isinstance(res, str):
            if not self.allow_new:
                await safe_response(ctx, f'{self.klass.__name__} `{argument}` not found', ephemeral=True)
                raise ValueError(f'{self.klass.__name__} `{argument}` not found')
            await safe_response(ctx, f'Searching for {argument}', ephemeral=True, delete_after=240)
            try:
                func = getattr(self.klass, self.from_argument_function_name, None)
                if func is None:
                    raise ValueError(f'No function {self.from_argument_function_name} found in {self.klass.__name__}')
                res = await func(argument)
            except Exception as e:
                await safe_response(ctx, f'Error searching for {argument}: {e}', ephemeral=True)
                raise ValueError(f'Error searching for {argument}: {e}')
        return res

    async def autocomplete(self, ctx: discord.Interaction, current: str):
        await safe_defer(ctx)

        if self.from_cache:
            cache = object_server_cache.setdefault(self.klass.__name__, {})
            objects = cache.get(ctx.guild.id, [])
            cl = current.lower()
            app = objects.copy()
            for flt in self.list_filters:
                app2 = []
                for obj in app:
                    if flt(obj, cl):
                        app2.append(obj)
                app = app2
            objects = app
            if len(objects) > MAX_AUTO_COMPLETE:
                return [app_commands.Choice(name=f'{len(objects)} items found', value=NONE_STR)]
        else:
            q = self.klass.objects
            for filter in self.query_filters:
                q = q.filter(filter(current))
            cnt = await q.acount()
            if cnt > MAX_AUTO_COMPLETE:
                return [app_commands.Choice(name=f'{cnt} items found', value=NONE_STR)]
            objects = [obj async for obj in q.all()]

        self.object_map = {str(getattr(s, self.map_attribute)): s for s in objects}

        return [
            app_commands.Choice(
                # name=f'[{s.duration}] {elide(s.title, 50)}',
                name=elide(await getattr(obj, self.descr_function_name)(self.verbose), length=90),
                value=str(getattr(obj, self.map_attribute))
            )
            for obj in objects
        ]

    @classmethod
    def register_cache(cls, server_id: int, objects: list):
        cache = object_server_cache.setdefault(cls.klass.__name__, {})
        for obj in objects:
            if not isinstance(obj, cls.klass):
                raise ValueError(f'Object {obj} is not an instance of {cls.klass.__name__}')
        cache[server_id] = objects.copy()

    @classmethod
    def remove_cache(cls, server_id: int):
        cache = object_server_cache.setdefault(cls.klass.__name__, {})
        cache.pop(server_id, None)


server_playlist_cache: dict[int, list[m.YTSong]] = {}
class SongTransformer(GenericObjectTransformer):
    klass = m.YTSong
    from_argument_function_name: str = 'from_search_string'
    descr_name = 'title'
    query_filters = [
        lambda x: Q(original_title__icontains=x) | Q(manual_title__icontains=x),
    ]
    list_filters = [
        lambda s, cl: cl in s.original_title.lower() or cl in (s.manual_title or '').lower(),
    ]
    map_attribute = 'youtube_id'
    # descr_function = lambda cls,s,vrb: f'[{s.duration}] {elide(s.title, 50)}'
    descr_function_name = 'get_str'


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

class AnimeTransformer(GenericObjectTransformer):
    klass = m.AnimeObj
    from_argument_function_name: str = 'from_string'
    list_filters = [
        lambda a, cl: cl in a.title.lower() or cl in (a.title_english or '').lower(),
    ]
    query_filters = [
        lambda x: Q(title__icontains=x) | Q(title_english__icontains=x),
    ]
    map_attribute = 'mal_id'
    # descr_function = lambda cls, a: f'{elide(a.title, 50)}'
    descr_function_name = 'get_str'

class AnimeCharacterTransformer(GenericObjectTransformer):
    klass = m.AnimeCharacter
    from_argument_function_name: str = 'from_string'
    list_filters = [
        lambda c, cl: cl in c.name.lower()
    ]
    query_filters = [
        lambda x: Q(name__icontains=x)
    ]
    map_attribute = 'mal_id'
    # descr_function = lambda cls, c: f'{elide(c.name, 50)}'
    descr_function_name = 'get_str'

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
