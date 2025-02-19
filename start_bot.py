"""Start the bot."""
import asyncio
import os

import discord
import django
from discord.ext import commands

# import concheddu_bot as cdbot

client = commands.Bot(
    command_prefix='!',
    intents=discord.Intents.default()
)


async def main():
    """Start the bot."""
    # os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bot_config.settings')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'concheddu_bot.settings')
    print('Django setup...')
    try:
        django.setup()
    except ModuleNotFoundError:
        print('Django settings not found')
        print(os.getcwd())
        return
    print('Django setup done')
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        raise ValueError('Token not found')

    @client.event
    async def on_ready():
        print(f'logged in successfully as {client.user.name}')
        # fmt = await bot.tree.sync()
        # print(f'Synced {fmt} commands')

    print('Starting bot...')
    async with client:
        await client.start(token)

if __name__ == '__main__':
    asyncio.run(main())
