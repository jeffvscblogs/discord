import discord
from discord.ext import commands, tasks
import json
import os
import asyncio
from datetime import datetime, timedelta

class Voice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.MONITORED_VC_FILE = "monitored_vcs.json"
        self.user_compliance = {}
        self.monitored_vcs = set()
        self.AFK_VC_ID = int(os.getenv("AFK_VC_ID"))
        self.ROLE_ID = int(os.getenv("COMPLIANCE_ROLE_ID"))
        
        self.load_monitored_vcs()
        self.check_compliance.start()

    def load_monitored_vcs(self):
        try:
            with open(self.MONITORED_VC_FILE, "r") as f:
                self.monitored_vcs = set(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            self.monitored_vcs = set()

    def save_monitored_vcs(self):
        with open(self.MONITORED_VC_FILE, "w") as f:
            json.dump(list(self.monitored_vcs), f)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return

        # Handle role assignment based on stream/camera
        await self.handle_role_assignment(member, after)
        
        # Compliance tracking
        await self.handle_compliance_tracking(member, before, after)

    async def handle_role_assignment(self, member, after):
        role = member.guild.get_role(self.ROLE_ID)
        if not role:
            return

        if after.channel and (after.self_stream or after.self_video):
            if role not in member.roles:
                await member.add_roles(role)
        elif role in member.roles:
            await member.remove_roles(role)

    async def handle_compliance_tracking(self, member, before, after):
        # Join monitored VC
        if after.channel and after.channel.id in self.monitored_vcs:
            if not before.channel or before.channel.id not in self.monitored_vcs:
                self.user_compliance[member.id] = {
                    "warn_count": 0,
                    "monitoring": True
                }
                await self.check_user_compliance(member)
                asyncio.create_task(self.schedule_compliance_check(member))

        # Leave monitored VC
        if before.channel and before.channel.id in self.monitored_vcs:
            if not after.channel or after.channel.id not in self.monitored_vcs:
                self.user_compliance.pop(member.id, None)

    async def schedule_compliance_check(self, member):
        await asyncio.sleep(60)
        if member.id in self.user_compliance:
            await self.check_user_compliance(member)

    @tasks.loop(seconds=60)
    async def check_compliance(self):
        guild = self.bot.get_guild(int(os.getenv("GUILD_ID")))
        role = guild.get_role(self.ROLE_ID)
        
        for user_id, status in list(self.user_compliance.items()):
            member = guild.get_member(user_id)
            if not member:
                continue

            if member.voice and member.voice.channel and member.voice.channel.id in self.monitored_vcs:
                if not (member.voice.self_stream or member.voice.self_video):
                    await self.handle_non_compliance(member)
                else:
                    status["warn_count"] = 0
            else:
                self.user_compliance.pop(user_id, None)

    async def handle_non_compliance(self, member):
        status = self.user_compliance[member.id]
        status["warn_count"] += 1
        
        if status["warn_count"] == 1:
            await self.send_warning(member, "First warning: Please turn on camera/screen share")
        elif status["warn_count"] == 2:
            await self.send_warning(member, "Final warning: Turn on camera within 60 seconds")
        elif status["warn_count"] >= 3:
            await self.move_to_afk(member)
            self.user_compliance.pop(member.id, None)

    async def send_warning(self, member, message):
        try:
            await member.send(message)
        except discord.Forbidden:
            pass

    async def move_to_afk(self, member):
        afk_channel = member.guild.get_channel(self.AFK_VC_ID)
        if afk_channel:
            try:
                await member.move_to(afk_channel)
            except discord.HTTPException:
                pass

    @commands.command()
    @commands.has_permissions(manage_channels=True)
    async def monitor_vc(self, ctx, action: str, channel: discord.VoiceChannel = None):
        action = action.lower()
        if action == "add" and channel:
            self.monitored_vcs.add(channel.id)
            await ctx.send(f"Added {channel.name} to monitored VCs")
        elif action == "remove" and channel:
            self.monitored_vcs.discard(channel.id)
            await ctx.send(f"Removed {channel.name} from monitored VCs")
        elif action == "list":
            channels = "\n".join([f"<#{vc_id}>" for vc_id in self.monitored_vcs])
            await ctx.send(f"Monitored VCs:\n{channels}")
        else:
            await ctx.send("Invalid action. Use add/remove/list")
        
        self.save_monitored_vcs()

    @check_compliance.before_loop
    async def before_check_compliance(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Voice(bot))