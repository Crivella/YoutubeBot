"""Start the bot."""
import asyncio
import os

import discord
import django
from discord.ext import commands

import concheddu_bot as cdbot

client = cdbot.bot.MyBot(
    command_prefix=commands.when_mentioned_or('!'),
    intents=discord.Intents.default()
    # intents=discord.Intents(
    #     voice_states=True, guilds=True, guild_messages=True, message_content=True
    # )
)

def main():
    """Start the bot."""
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

    # @client.event
    # async def on_ready():
    #     print(f'logged in successfully as {client.user.name}')
    #     # fmt = await bot.tree.sync()
    #     # print(f'Synced {fmt} commands')

    print('Starting bot...')
    client.add_cog(cdbot.bot.Music(client))
    client.run(token)

if __name__ == '__main__':
    main()
