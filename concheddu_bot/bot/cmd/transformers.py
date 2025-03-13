"""Music commands for the bot"""
import logging

import discord
from discord import app_commands

from ... import models as m
from ...models import filters as flt
from ..utils import safe_defer, safe_response
from ..views.utils import elide

logger = logging.getLogger('bot')

MAX_AUTO_COMPLETE = 10

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

class SongTransformer(app_commands.Transformer):
    def __init__(
            self, *args,
            allow_new: bool = False,
            nullable: bool = False,
            **kwargs
        ):
        super().__init__(*args, **kwargs)
        self.song_map = {}
        self.allow_new = allow_new
        self.nullable = nullable

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
            song = await m.YTSong.from_search_string(argument)
        return song

    async def autocomplete(self, ctx: discord.Interaction, current: str):
        await safe_defer(ctx)
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

class SongFilterTransformer(app_commands.Transformer):
    async def transform(self, ctx: discord.Interaction, argument: str):
        return argument

    async def autocomplete(self, ctx: discord.Interaction, current: str):
        return [
            app_commands.Choice(name=flt.song_order_descr[k], value=k) for k in flt.song_order_map.keys()
            if k.startswith(current)
        ]

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

        return res
