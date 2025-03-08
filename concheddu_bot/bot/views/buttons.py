import discord

from ..utils import ensure_response


class CallbackButton(discord.ui.Button):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.callbacks = []

    def add_callback(self, callback):
        self.callbacks.append(callback)

    @ensure_response(before=True, defer=True)
    async def callback(self, itc: discord.Interaction):
        for callback in self.callbacks:
            await callback(itc)
