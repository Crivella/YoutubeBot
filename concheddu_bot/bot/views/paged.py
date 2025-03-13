import discord

from ... import models as m
from ..utils import ensure_response, safe_response, sense_check
from .buttons import CallbackButton
from .utils import MAX_LIST_OPT, elide, logger


class SongOption(discord.SelectOption):
    def __init__(self, song: m.YTSong, *args,**kwargs):
        super().__init__(
            label=elide(song.title),
            value=song.youtube_id,
            description=f'[{song.duration} s] [{song.times_played} plays]',
            # description=f'[{song.duration} s]',
            emoji='🎵',
            *args, **kwargs
        )
        self.song = song

class Paged:
    def __init__(self, view: discord.ui.View, *args, **kwargs):
        super().__init__(*args, **kwargs)

        btn_row = kwargs.get('row', 0) + 1

        self.fst_btn = CallbackButton(label='<<', row=btn_row, style=discord.ButtonStyle.primary)
        self.bwd_btn = CallbackButton(label='<', row=btn_row, style=discord.ButtonStyle.primary)
        self.pge_btn = CallbackButton(label='1', row=btn_row, disabled=True, style=discord.ButtonStyle.secondary)
        self.fwd_btn = CallbackButton(label='>', row=btn_row, style=discord.ButtonStyle.primary)
        self.lst_btn = CallbackButton(label='>>', row=btn_row, style=discord.ButtonStyle.primary)

        self.fst_btn.add_callback(lambda *args: self.go_to_page(0))
        self.bwd_btn.add_callback(self.page_backward)
        self.fwd_btn.add_callback(self.page_forward)
        self.lst_btn.add_callback(lambda *args: self.go_to_page(self.num_pages))
        self.pge_btn.disabled = True

        view.add_item(self.fst_btn)
        view.add_item(self.bwd_btn)
        view.add_item(self.pge_btn)
        view.add_item(self.fwd_btn)
        view.add_item(self.lst_btn)

        self.page = None
        self.options__: list = []
        self.num_pages = 0
        self.follow_changes = False

    @property
    def options_(self):
        return self.options__
    @options_.setter
    def options_(self, value):
        self.options__ = value
        self.num_pages = (len(value) - 1) // MAX_LIST_OPT

    async def page_forward(self, *args):
        return await self.go_to_page(self.page + 1)

    async def page_backward(self, *args):
        return await self.go_to_page(self.page - 1)

    async def go_to_page(self, page: int) -> bool:
        logger.debug(f'go_to_page: {page} / {self.num_pages} , {self.page}')
        if page < 0 or page > self.num_pages:
            return False
        if page == self.page:
            return True
        self.page = page
        start = page * MAX_LIST_OPT
        end = start + MAX_LIST_OPT

        lst = self.options_[start:end]
        if self.follow_changes:
            self.max_values = min(MAX_LIST_OPT, len(lst))
        self.options = lst

        self.fst_btn.disabled = page <= 0
        self.bwd_btn.disabled = page <= 0
        self.fwd_btn.disabled = page >= self.num_pages
        self.lst_btn.disabled = page >= self.num_pages
        self.pge_btn.label = f'{page+1} / {self.num_pages+1}'
        await safe_response(self.view.itc, view=self.view)

class ListPlay(Paged, discord.ui.Select):
    def __init__(
            self,
            songs: list[m.YTSong],
            *args,
            **kwargs
        ):
        logger.debug(f'ListPlay: {len(songs)}')
        opts = [SongOption(song) for song in songs]
        super().__init__(
            placeholder='Select a song to play',
            min_values=0,
            max_values=1,
            options=opts[:MAX_LIST_OPT],
            *args, **kwargs
        )
        self.follow_changes = False

        self.options_ = opts
        self.songs_map = {opt.value: opt.song for opt in opts}

    @sense_check
    @ensure_response(before=False, defer=True)
    async def callback(self, itc: discord.Interaction):
        if not self.values:
            return
        song_id = self.values[0]
        song = self.songs_map.get(song_id)

        await song.play(itc=itc)

class ListMultiSelect(Paged, discord.ui.Select):
    def __init__(self, songs: list[m.YTSong], defaults: list[m.YTSong] = None, *args, **kwargs):
        defaults = defaults or []
        logger.debug(f'ListMultiSelect: {len(songs)}')
        opts = [SongOption(song) for song in songs]
        for opt in opts:
            opt.default = opt.song in defaults
        super().__init__(
            placeholder='Select a song to play',
            options=opts[:MAX_LIST_OPT],
            *args, **kwargs
        )
        self.follow_changes = True
        self.options_ = opts
        self.songs_map = {opt.value: opt.song for opt in opts}

    @ensure_response(before=False, defer=True)
    async def callback(self, itc: discord.Interaction):
        values = set(self.values)
        for opt in self.options_[self.page * MAX_LIST_OPT:(self.page + 1) * MAX_LIST_OPT]:
            opt.default = opt.value in values

class ListQuiz(Paged, discord.ui.Select):
    def __init__(self, quizes: list[m.QuizSong], *args, **kwargs):
        logger.debug(f'ListQuiz: {len(quizes)}')
        opts = [
            discord.SelectOption(
                label=elide(f'{quiz.__class__.__name__} {quiz.date_start}'),
                value=str(quiz.id),
                description=f'{quiz.num_songs} songs, {quiz.num_choices} choices',
                emoji='❓'
            ) for quiz in quizes
        ]
        super().__init__(
            placeholder='Select a quiz to play',
            options=opts[:MAX_LIST_OPT],
            min_values=1,
            max_values=1,
            *args, **kwargs
        )
        self.options_ = opts
        self.quizes_map = {quiz.id: quiz for quiz in quizes}

    @ensure_response(before=False, defer=True)
    async def callback(self, itc: discord.Interaction):
        if not self.values:
            return
        quiz_id = int(self.values[0])
        quiz = self.quizes_map.get(quiz_id)
        embed = await quiz.get_embed()
        await safe_response(itc, embed=embed, ephemeral=True, delete_after=60)
