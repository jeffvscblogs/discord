from discord.ext import commands
import psutil

class Utilities(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def ping(self, ctx):
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"Pong! Latency: {latency}ms")

    @commands.command()
    async def health(self, ctx):
        # Keep your health check implementation here
        pass

async def setup(bot):
    await bot.add_cog(Utilities(bot))