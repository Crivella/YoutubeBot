import discord

from ...utils import ensure_response
from ..utils import elide, logger


async def get_object_thumbnail(obj):
    """Get the thumbnail for an object"""
    try:
        res = await obj.get_thumbnail()
    except Exception as e:
        logger.error(f'Error getting thumbnail for {obj}: {e}')
        res = None
    return res

class UserList(discord.ui.Select):
    def __init__(self, users: list[discord.Member], *args, **kwargs):
        super().__init__(
            placeholder='Select a user',
            options=[
                discord.SelectOption(
                    label=elide(user.name),
                    value=user.id,
                    emoji='👤'
                ) for user in users
            ],
            *args, **kwargs
        )
        self.map = {str(user.id): user for user in users}

    @ensure_response(before=False, defer=True)
    async def callback(self, itc: discord.Interaction):
        pass

    def get_users(self):
        return [self.map[user_id] for user_id in self.values]
