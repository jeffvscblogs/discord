import discord
from discord.ext import commands
import psutil
import os
import aiohttp
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

class Utilities(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.GUILD_ID = int(os.getenv("GUILD_ID"))
        self.MOD_LOG_CHANNEL_ID = int(os.getenv("MOD_LOG_CHANNEL_ID"))

    @commands.command()
    async def ping(self, ctx):
        """Check bot latency"""
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(
            title="Pong! 🏓",
            description=f"Latency: {latency}ms",
            color=0x00ff00
        )
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_any_role("Admin", "Moderator")
    async def health(self, ctx):
        """System health check"""
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        embed = discord.Embed(title="System Health", color=0x7289da)
        embed.add_field(name="CPU Usage", value=f"{cpu}%", inline=False)
        embed.add_field(name="Memory Usage", 
                      value=f"{mem.percent}% ({mem.used//1024**2}MB/{mem.total//1024**2}MB)", 
                      inline=False)
        embed.add_field(name="Disk Usage", 
                      value=f"{disk.percent}% ({disk.used//1024**3}GB/{disk.total//1024**3}GB)", 
                      inline=False)
        
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_any_role("Admin", "Moderator")
    async def send_dm(self, ctx, member: discord.Member, *, message: str):
        """Send direct message to a user"""
        try:
            await member.send(message)
            await ctx.send(f"Message sent to {member.mention}")
        except discord.Forbidden:
            await ctx.send("Could not send DM - user has DMs disabled")

    @commands.command()
    @commands.has_any_role("Moderator")
    async def send_invwarn(self, ctx, member: discord.Member):
        """Send invite warning to user"""
        embed = discord.Embed(
            title="⚠️ Invite Warning",
            description=(
                "Sharing server invites is prohibited. Repeated violations "
                "may result in a ban. Please review our server rules."
            ),
            color=0xff0000
        )
        
        try:
            await member.send(embed=embed)
            await ctx.send(f"Warning sent to {member.mention}")
        except discord.Forbidden:
            await ctx.send("Could not send warning - user has DMs disabled")

    @commands.command()
    @commands.has_any_role("Admin")
    async def send_message(self, ctx, channel_id: int, *, message: str):
        """Send message to specific channel"""
        channel = self.bot.get_channel(channel_id)
        
        if not channel:
            return await ctx.send("Invalid channel ID")

        # Check permissions
        if not channel.permissions_for(ctx.author).send_messages:
            return await ctx.send("You don't have permission here")

        # Handle attachments
        file = None
        if ctx.message.attachments:
            async with aiohttp.ClientSession() as session:
                async with session.get(ctx.message.attachments[0].url) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        file = discord.File(io.BytesIO(data), 
                                           filename=ctx.message.attachments[0].filename)

        # Handle different channel types
        if isinstance(channel, discord.TextChannel):
            await channel.send(content=message, file=file)
        elif isinstance(channel, discord.VoiceChannel):
            logs = self.bot.get_channel(self.MOD_LOG_CHANNEL_ID)
            await logs.send(f"Voice Channel Announcement ({channel.name}): {message}", file=file)
        
        await ctx.send("Message delivered ✅")

    @commands.command()
    async def rule(self, ctx):
        """Display study room rules"""
        embed = discord.Embed(
            title="📚 Study Room Rules",
            color=0x00ff00
        )
        embed.add_field(
            name="1. Camera/Screen Share",
            value="Enable camera or screen sharing to stay in voice channels",
            inline=False
        )
        embed.add_field(
            name="2. Allowed Commands",
            value="Use `/pomodoro`, `/list` for study management",
            inline=False
        )
        embed.add_field(
            name="3. Maintain Focus",
            value="Keep conversations study-related and respectful",
            inline=False
        )
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_any_role("Admin", "Moderator")
    async def apologize(self, ctx):
        """Send official apology"""
        embed = discord.Embed(
            title="Official Apology",
            description="We sincerely apologize for any inconvenience caused.",
            color=0xff0000
        )
        await ctx.send(embed=embed)

    @send_message.error
    @send_dm.error
    async def util_error(self, ctx, error):
        if isinstance(error, commands.MissingRole):
            await ctx.send("Missing required role!")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Missing required arguments!")
        else:
            await ctx.send(f"Error: {str(error)}")

async def setup(bot):
    await bot.add_cog(Utilities(bot))
