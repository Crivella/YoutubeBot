"""Start the bot."""
import asyncio
import os
import signal
import sys

import discord
import django
from discord.ext import commands
from django.core.management import call_command

client = None

def get_bot():
    global client
    if client is None:
        # This needs to be imported after django.setup()
        #pylint: disable=import-outside-toplevel
        from concheddu_bot.bot import MyBot
        client = MyBot(
            command_prefix=commands.when_mentioned_or('!'),
            intents=discord.Intents.default()
            # intents=discord.Intents(
            #     voice_states=True, guilds=True, guild_messages=True, message_content=True
            # )
        )
    return client

def main():
    """Start the bot."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'concheddu_bot.settings')
    print('Django setup...')
    try:
        django.setup()
    except ModuleNotFoundError:
        print('Django settings not found')
        print(os.getcwd())
        raise
        return
    print('Django setup done')

    print('Create database (if needed) and apply database migrations (if any)...')
    call_command('migrate')
    print('Database setup done')

    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        raise ValueError('Token not found')

    from concheddu_bot.bot import cmd
    print('Starting bot...')
    bot = get_bot()
    asyncio.run(bot.add_cog(cmd.Music()))
    asyncio.run(bot.add_cog(cmd.MusicPlayer()))
    asyncio.run(bot.add_cog(cmd.Playlists()))
    asyncio.run(bot.add_cog(cmd.QuizSong()))
    # asyncio.run(bot.add_cog(cmd.QuizSongText()))
    asyncio.run(bot.add_cog(cmd.Admin(bot=bot)))
    bot.run(token)

if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
    main()
