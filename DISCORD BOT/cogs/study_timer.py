import discord
from discord.ext import commands, tasks
import json
import os
import datetime
import pytz
import asyncio

class StudyTimer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.DATA_FILE = "study_channels.json"
        self.channels = self.load_data()
        self.timezone = pytz.timezone("Asia/Kolkata")
        self.scheduled_update.start()

    def load_data(self):
        if os.path.exists(self.DATA_FILE):
            with open(self.DATA_FILE, "r") as f:
                return json.load(f)
        return {}

    def save_data(self):
        with open(self.DATA_FILE, "w") as f:
            json.dump(self.channels, f, indent=4)

    def get_days_left(self, exam_date_str):
        exam_date = datetime.datetime.fromisoformat(exam_date_str).astimezone(self.timezone)
        today = datetime.datetime.now(self.timezone).replace(hour=0, minute=0, second=0, microsecond=0)
        delta = (exam_date - today).days
        return max(delta, 0)

    async def update_channel_names(self):
        guild = self.bot.get_guild(int(os.getenv("GUILD_ID")))
        if not guild:
            return

        for channel_id, channel_data in self.channels.items():
            try:
                channel = guild.get_channel(int(channel_id))
                if not channel:
                    continue

                days_left = self.get_days_left(channel_data["date"])
                new_name = f"{channel_data['exam']} : {days_left} Days"

                if channel.name != new_name:
                    await channel.edit(name=new_name)
            except Exception as e:
                print(f"Error updating channel {channel_id}: {e}")

    @tasks.loop(hours=24)
    async def scheduled_update(self):
        await self.update_channel_names()

    @scheduled_update.before_loop
    async def before_scheduled_update(self):
        await self.bot.wait_until_ready()
        now = datetime.datetime.now(self.timezone)
        midnight = now.replace(hour=0, minute=0, second=0) + datetime.timedelta(days=1)
        delay = (midnight - now).total_seconds()
        await asyncio.sleep(delay)

    @commands.Cog.listener()
    async def on_ready(self):
        await self.update_channel_names()

    @discord.app_commands.command(name="setexam", description="Set exam date for a voice channel")
    @discord.app_commands.describe(
        channel="Voice channel to monitor",
        exam_name="Name of the exam/course",
        exam_date="Exam date (YYYY-MM-DD)"
    )
    async def set_exam(self, interaction: discord.Interaction, 
                      channel: discord.VoiceChannel,
                      exam_name: str,
                      exam_date: str):
        try:
            # Validate date format
            date_obj = datetime.datetime.strptime(exam_date, "%Y-%m-%d")
            date_obj = self.timezone.localize(date_obj)
            
            self.channels[str(channel.id)] = {
                "exam": exam_name,
                "date": date_obj.isoformat()
            }
            self.save_data()

            days_left = self.get_days_left(date_obj.isoformat())
            await channel.edit(name=f"{exam_name} : {days_left} Days")

            await interaction.response.send_message(
                f"✅ {channel.mention} will count down to {exam_date}",
                ephemeral=True
            )
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid date format. Use YYYY-MM-DD",
                ephemeral=True
            )

    @discord.app_commands.command(name="removeexam", description="Remove exam tracking from a voice channel")
    @discord.app_commands.describe(channel="Voice channel to remove")
    async def remove_exam(self, interaction: discord.Interaction, channel: discord.VoiceChannel):
        channel_id = str(channel.id)
        if channel_id in self.channels:
            del self.channels[channel_id]
            self.save_data()
            await channel.edit(name=channel.name.split(" : ")[0])
            await interaction.response.send_message(
                f"✅ Removed exam tracking from {channel.mention}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ {channel.mention} isn't being tracked",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(StudyTimer(bot))