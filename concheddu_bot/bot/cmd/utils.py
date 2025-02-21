"""Music commands for the bot"""
import discord
from discord import app_commands
from discord.ext import commands


class ServerUtils(commands.Cog):
    """Play command"""
    @app_commands.command()
    async def sync(self, itc: discord.Interaction):
        """Sync the bot commands"""
        fmt = await self.bot.tree.sync(guild=itc.guild)
        print(f'Synced {fmt} commands')
        await itc.response.send_message(f'Synced {fmt} commands')
