import asyncio
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.voice_states = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

async def load_cogs():
    await bot.load_extension("cogs.moderation")
    await bot.load_extension("cogs.tickets")
    await bot.load_extension("cogs.voice")
    await bot.load_extension("cogs.study_timer")
    await bot.load_extension("cogs.roles")
    await bot.load_extension("cogs.utilities")

@bot.event
async def on_ready():
    print(f'Bot connected as {bot.user.name}')

async def main():
    await load_cogs()
    await bot.start(os.getenv('TOKEN'))

if __name__ == "__main__":
    asyncio.run(main())