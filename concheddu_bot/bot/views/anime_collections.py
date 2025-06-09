import discord

from ... import models as m
from ..buttons import CallbackButton
from ..utils import ensure_response, safe_response
from .paged import AnimeOption, ListMultiSelect
from .utils import MAX_LIST_OPT, logger


class EditAnimeCollection(discord.ui.View):
    def __init__(
            self,
            itc: discord.Interaction,
            collection: m.AnimeCollection, anime_Lst: list[m.AnimeObj], defaults: list[m.AnimeObj] = None,
            new_name: str = None
        ):
        super().__init__()
        defaults = defaults or []
        self.itc = itc
        self.collection = collection

        if not anime_Lst:
            self.add_item(discord.ui.Button(
                label='No songs found',
                style=discord.ButtonStyle.secondary,
                disabled=True
            ))
            return

        lst = defaults.copy()
        for anime in anime_Lst:
            if anime not in defaults:
                lst.append(anime)

        mv = min(MAX_LIST_OPT, len(anime_Lst))
        self.list = ListMultiSelect(
            AnimeOption,
            lst,
            defaults,
            row=1, min_values=0, max_values=mv,
            view = self,
        )

        async def submit_callback(itc: discord.Interaction):
            logger.info(f'Editing anime collection `{collection.name}`:')
            added = 0
            removed = 0
            for opt in self.list.options_:
                if opt.default:
                    logger.debug(f'  PRESENT - {opt.obj.title}')
                    added += await collection.add_anime(opt.obj)
                else:
                    logger.debug(f'  ABSENT - {opt.obj.title}')
                    removed += await collection.remove_anime(opt.obj)
            total = await collection.animes.acount()
            msg = [f'Collection `{collection.name}` edited ADDED: {added} - REMOVED: {removed} - TOTAL: {total}']
            if new_name:
                await collection.rename(new_name)
                msg.append(f'Playlist renamed to `{new_name}`')
            self.clear_items()
            await safe_response(itc, '\n'.join(msg), view=None)

        self.submit = CallbackButton(
            label='Submit',
            style=discord.ButtonStyle.primary,
            row=3
        )
        self.submit.add_callback(submit_callback)

        self.add_item(self.list)
        self.add_item(self.submit)

    async def on_timeout(self):
        await self.itc.delete_original_response()

class DeletePlaylist(discord.ui.View):
    def __init__(self, itc: discord.Interaction, playlist: m.Playlist):
        super().__init__()
        self.itc = itc
        self.playlist = playlist

        delete = CallbackButton(
            label='Delete playlist',
            style=discord.ButtonStyle.danger
        )
        nop = CallbackButton(
            label='Cancel',
            style=discord.ButtonStyle.secondary
        )

        @ensure_response(before=False, defer=True)
        async def submit_callback(itc: discord.Interaction):
            await self.playlist.adelete()
            await safe_response(
                self.itc,
                content=f'Playlist `{self.playlist.name}` deleted',
                view=None
            )

        @ensure_response(before=False, defer=True)
        async def cancel_callback(itc: discord.Interaction):
            await self.itc.delete_original_response()

        delete.add_callback(submit_callback)
        nop.add_callback(cancel_callback)
        self.add_item(delete)
        self.add_item(nop)

    async def on_timeout(self):
        await self.itc.delete_original_response()
