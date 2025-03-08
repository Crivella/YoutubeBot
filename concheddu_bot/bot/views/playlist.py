import discord

from ... import models as m
from ..utils import safe_response
from .buttons import CallbackButton
from .paged import ListMultiSelect, ListMultiSelect2
from .utils import MAX_LIST_OPT, logger


class CreatePlaylist(discord.ui.View):
    def __init__(self, itc: discord.Interaction, songs: list[m.YTSong], name):
        super().__init__()
        self.itc = itc

        # self.songs = songs
        self.name_ = name

        if not songs:
            self.add_item(discord.ui.Button(
                label='No songs found',
                style=discord.ButtonStyle.secondary,
                disabled=True
            ))
            return

        mv = min(MAX_LIST_OPT, len(songs))
        # btn = ButtonPageNum(row=2)
        bwd_btn = CallbackButton(label='<', row=2, style=discord.ButtonStyle.primary)
        pge_btn = CallbackButton(label='1', row=2, disabled=True, style=discord.ButtonStyle.secondary)
        fwd_btn = CallbackButton(label='>', row=2, style=discord.ButtonStyle.primary)
        self.list = ListMultiSelect(
            songs, row=1, min_values=0, max_values=mv,
            bwd_btn=bwd_btn, pge_btn=pge_btn, fwd_btn=fwd_btn
            )

        async def submit_callback(itc: discord.Interaction):
            playlist = await m.Playlist.create_playlist(self.name_, server=itc.guild, user=itc.user)
            logger.info(f'Creating playlist `{self.name_}`:')
            for opt in self.list.options_:
                if opt.default:
                    logger.info(f'  - {opt.song.title}')
                    # print(f'Adding {opt.song.title} to playlist')
                    await playlist.add_song(opt.song)
            await itc.response.send_message(
                f'Playlist `{self.name_}` created',
                ephemeral=True
            )

        self.submit = CallbackButton(
            label='Submit',
            style=discord.ButtonStyle.primary,
            row=3
        )
        self.submit.add_callback(submit_callback)

        self.add_item(self.list)
        self.add_item(bwd_btn)
        self.add_item(pge_btn)
        self.add_item(fwd_btn)
        self.add_item(self.submit)

    async def on_timeout(self):
        await self.itc.delete_original_response()


class EditPlaylist(discord.ui.View):
    def __init__(
            self,
            itc: discord.Interaction,
            playlist: m.Playlist, songs: list[m.YTSong], defaults: list[m.YTSong],
            new_name: str = None
        ):
        super().__init__()
        self.itc = itc
        self.playlist = playlist

        if not songs:
            self.add_item(discord.ui.Button(
                label='No songs found',
                style=discord.ButtonStyle.secondary,
                disabled=True
            ))
            return

        lst = defaults.copy()
        for song in songs:
            if song not in defaults:
                lst.append(song)

        mv = min(MAX_LIST_OPT, len(songs))
        bwd_btn = CallbackButton(label='<', row=2, style=discord.ButtonStyle.primary)
        pge_btn = CallbackButton(label='1', row=2, disabled=True, style=discord.ButtonStyle.secondary)
        fwd_btn = CallbackButton(label='>', row=2, style=discord.ButtonStyle.primary)
        self.list = ListMultiSelect2(
            lst,
            defaults,
            row=1, min_values=0, max_values=mv,
            bwd_btn=bwd_btn, pge_btn=pge_btn, fwd_btn=fwd_btn
        )

        async def submit_callback(itc: discord.Interaction):
            logger.info(f'Editing playlist `{playlist.name}`:')
            added = 0
            removed = 0
            for opt in self.list.options_:
                if opt.default:
                    logger.debug(f'  PRESENT - {opt.song.title}')
                    added += await playlist.add_song(opt.song)
                else:
                    logger.debug(f'  ABSENT - {opt.song.title}')
                    removed += await playlist.remove_song(opt.song)
            total = await playlist.songs.acount()
            msg = [f'Playlist `{playlist.name}` edited ADDED: {added} - REMOVED: {removed} - TOTAL: {total}']
            if new_name:
                await playlist.rename(new_name)
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
        self.add_item(bwd_btn)
        self.add_item(pge_btn)
        self.add_item(fwd_btn)
        self.add_item(self.submit)

    async def on_timeout(self):
        await self.itc.delete_original_response()
