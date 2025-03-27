import discord
from discord.ext import commands
import re
import json
import os
from datetime import datetime

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.NSFW_KEYWORDS = [
            "cock", "deepthroat", "dick", "cumshot", "fuck", "sperm",
            "jerk off", "naked", "ass", "tits", "fingering", "masturbate",
            # ... (rest of your NSFW keywords)
        ]
        self.WARNINGS_FILE = 'warnings.json'
        self.MUTE_ROLE_ID = int(os.getenv("MUTE_ROLE_ID"))
        self.ABUSE_LOG_CHANNEL_ID = int(os.getenv("ABUSE_LOG_CHANNEL_ID"))
        self.MOD_LOG_CHANNEL_ID = int(os.getenv("MOD_LOG_CHANNEL_ID"))
        self.user_warnings = self.load_warnings()

    def load_warnings(self):
        if os.path.exists(self.WARNINGS_FILE):
            with open(self.WARNINGS_FILE, 'r') as f:
                return json.load(f)
        return {}

    def save_warnings(self):
        with open(self.WARNINGS_FILE, 'w') as f:
            json.dump(self.user_warnings, f, indent=4)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or isinstance(message.channel, discord.DMChannel):
            return

        if await self.check_nsfw_content(message.content):
            await self.handle_nsfw_message(message)
            await message.delete()

    async def check_nsfw_content(self, content):
        content_lower = content.lower()
        return any(re.search(rf'\b{re.escape(keyword)}\b', content_lower) 
                for keyword in self.NSFW_KEYWORDS)

    async def handle_nsfw_message(self, message):
        mute_role = message.guild.get_role(self.MUTE_ROLE_ID)
        if mute_role:
            try:
                await message.author.add_roles(mute_role)
                
                # User notification
                try:
                    embed = discord.Embed(
                        title="Content Violation",
                        description="You've been muted for posting inappropriate content.",
                        color=discord.Color.red()
                    )
                    await message.author.send(embed=embed)
                except discord.Forbidden:
                    pass

                # Log to abuse channel
                log_channel = message.guild.get_channel(self.ABUSE_LOG_CHANNEL_ID)
                if log_channel:
                    embed = discord.Embed(
                        title="NSFW Content Detected",
                        description=f"{message.author.mention} posted restricted content",
                        color=discord.Color.orange()
                    )
                    embed.add_field(name="Message", value=message.content[:500], inline=False)
                    embed.add_field(name="Action", value="Muted + Message Deleted")
                    await log_channel.send(embed=embed)

            except discord.Forbidden:
                pass

    @commands.command()
    @commands.has_any_role("Admin", "Moderator")  # Update with your role names
    async def warn(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        user_id = str(member.id)
        self.user_warnings[user_id] = self.user_warnings.get(user_id, 0) + 1
        self.save_warnings()

        # Check for mute threshold
        if self.user_warnings[user_id] >= 5:
            mute_role = ctx.guild.get_role(self.MUTE_ROLE_ID)
            if mute_role:
                await member.add_roles(mute_role)
                self.user_warnings.pop(user_id, None)
                self.save_warnings()

        # Send confirmation
        embed = discord.Embed(
            title="Warning Issued",
            description=f"{member.mention} has been warned",
            color=discord.Color.yellow()
        )
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Total Warnings", value=self.user_warnings.get(user_id, 0))
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_any_role("Admin", "Moderator")
    async def mute(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        mute_role = ctx.guild.get_role(self.MUTE_ROLE_ID)
        if not mute_role:
            return await ctx.send("Mute role not configured")

        if mute_role in member.roles:
            return await ctx.send("User is already muted")

        await member.add_roles(mute_role)
        embed = discord.Embed(
            title="User Muted",
            description=f"{member.mention} has been muted",
            color=discord.Color.red()
        )
        embed.add_field(name="Reason", value=reason)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_any_role("Admin", "Moderator")
    async def unmute(self, ctx, member: discord.Member):
        mute_role = ctx.guild.get_role(self.MUTE_ROLE_ID)
        if not mute_role:
            return await ctx.send("Mute role not configured")

        if mute_role not in member.roles:
            return await ctx.send("User is not muted")

        await member.remove_roles(mute_role)
        embed = discord.Embed(
            title="User Unmuted",
            description=f"{member.mention} has been unmuted",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.command()
    async def warnings(self, ctx, member: discord.Member):
        warnings = self.user_warnings.get(str(member.id), 0)
        embed = discord.Embed(
            title="Warning History",
            description=f"{member.mention} has {warnings} warnings",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_any_role("Admin", "Moderator")
    async def del_warn(self, ctx, member: discord.Member, count: int = 1):
        user_id = str(member.id)
        current = self.user_warnings.get(user_id, 0)
        new_count = max(current - count, 0)
        
        if new_count == 0:
            self.user_warnings.pop(user_id, None)
        else:
            self.user_warnings[user_id] = new_count
        
        self.save_warnings()
        
        embed = discord.Embed(
            title="Warnings Removed",
            description=f"Removed {count} warnings from {member.mention}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Moderation(bot))