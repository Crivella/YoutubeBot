# import discord

# from discord import app_commands
# from discord.ext import commands, tasks

# from ..import models as m
# from ..import youtube as yt

# class Play(commands.Cog):
#     """Play command"""
#     def __init__(self, bot: commands.Bot):
#         self.bot = bot

#     @app_commands.command()
#     # @commands.command()
#     async def play(self, itc: discord.Interaction, search: str):
#         """Play a song"""
#         user_dc = itc.user
#         voice
#         source = await yt.YTDLSource.from_url(search, loop=self.bot.loop)
#         song, _ = m.YTSong.objects.get_or_create(
#             youtube_id=source.data['id']
#             )
#         for attr in ['title', 'duration']:
#             setattr(song, attr, source.data[attr])
#         song.save()

#         await itc.response.send_message(f'Playing {source.data["title"]}')
#         await self.bot.play_song(itc, source)

#     async def sense_check(self, itc: discord.Interaction) -> bool:
#         """Check if the user is in a voice channel"""
#         user_dc = itc.user
#         if not user_dc.voice:
#             await itc.response.send_message(
#                 'You must be in a voice channel to use this command',
#                 ephemeral=True
#             )
#             return False
#         if self.bot.id not in [m.id for m in user_dc.voice.channel.members]:
#             await itc.response.send_message(
#                 'I must be in the same voice channel as you to use this command',
#                 ephemeral=True
#             )
#             return False
#         return True
