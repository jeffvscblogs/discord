import discord
from discord.ext import commands
from discord.ui import Select, Button, View, Modal, TextInput
import json
import os
import base64
import requests
import datetime
import asyncio
from jinja2 import Environment, BaseLoader

# Custom filter function
def replace_mentions_filter(content, users):
    for user_id, username in users.items():
        content = content.replace(f"<@{user_id}>", f"@{username}")
        content = content.replace(f"<@!{user_id}>", f"@{username}")
    return content

# Create Jinja2 environment with custom filter
env = Environment(loader=BaseLoader)
env.filters['replace_mentions'] = replace_ments_filter

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.TICKETS_FILE = "tickets.json"
        self.TICKET_COUNTER_FILE = "ticket_counter.txt"
        self.TICKET_CREATION_MESSAGE_FILE = "ticket_creation_message_id.txt"
        self.tickets = {}
        self.ticket_counter = 0
        self.TICKET_CREATION_MESSAGE_ID = None
        self.TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID"))
        self.TRANSCRIPTS_CHANNEL_ID = int(os.getenv("TRANSCRIPTS_CHANNEL_ID"))
        self.SUPPORT_ROLE_ID = int(os.getenv("SUPPORT_ROLE_ID"))
        self.GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
        
        self.load_data()
        self.bot.loop.create_task(self.setup_ticket_creation_message())

    def load_data(self):
        # Load ticket counter
        if os.path.exists(self.TICKET_COUNTER_FILE):
            with open(self.TICKET_COUNTER_FILE, "r") as f:
                self.ticket_counter = int(f.read().strip())
                
        # Load ticket creation message ID
        if os.path.exists(self.TICKET_CREATION_MESSAGE_FILE):
            with open(self.TICKET_CREATION_MESSAGE_FILE, "r") as f:
                self.TICKET_CREATION_MESSAGE_ID = int(f.read().strip())
        
        # Load existing tickets
        if os.path.exists(self.TICKETS_FILE):
            with open(self.TICKETS_FILE, "r") as f:
                self.tickets = json.load(f)

    def save_data(self):
        # Save ticket counter
        with open(self.TICKET_COUNTER_FILE, "w") as f:
            f.write(str(self.ticket_counter))
            
        # Save ticket creation message ID
        with open(self.TICKET_CREATION_MESSAGE_FILE, "w") as f:
            if self.TICKET_CREATION_MESSAGE_ID:
                f.write(str(self.TICKET_CREATION_MESSAGE_ID))
        
        # Save tickets
        with open(self.TICKETS_FILE, "w") as f:
            json.dump(self.tickets, f, indent=4)

    class StaffApplicationModal(Modal, title="Staff Application"):
        def __init__(self, cog):
            super().__init__()
            self.cog = cog
            self.role = TextInput(label="Applying for which role?", required=True)
            self.studying = TextInput(label="What are you currently studying for?", required=True)
            self.timings = TextInput(label="Active timings?", required=True)
            self.cam_preference = TextInput(label="Prefer cam/non-cam sessions?", required=True)
            self.experience = TextInput(label="Past experiences in moderation?", required=True)

        async def on_submit(self, interaction: discord.Interaction):
            await self.cog.create_ticket(interaction, "apply_for_staff", self)

    class CloseTicketModal(Modal, title="Close Ticket"):
        def __init__(self, cog, ticket_id):
            super().__init__()
            self.cog = cog
            self.ticket_id = ticket_id
            self.reason = TextInput(label="Reason for closing", style=discord.TextStyle.long)

        async def on_submit(self, interaction: discord.Interaction):
            await self.cog.close_ticket(interaction, self.ticket_id, self.reason.value)

    async def setup_ticket_creation_message(self):
        channel = self.bot.get_channel(int(os.getenv("TICKET_CREATION_CHANNEL_ID")))
        if not channel:
            return

        # Recreate dropdown view
        select = Select(
            placeholder="Select your issue",
            options=[
                discord.SelectOption(label="Help Desk", value="help_desk", emoji="🛠️"),
                discord.SelectOption(label="Apply for Staff", value="apply_for_staff", emoji="📝"),
                discord.SelectOption(label="Request of Ban", value="request_of_ban", emoji="🔒"),
            ]
        )

        async def select_callback(interaction):
            if select.values[0] == "apply_for_staff":
                await interaction.response.send_modal(self.StaffApplicationModal(self))
            else:
                await self.create_ticket(interaction, select.values[0])

        select.callback = select_callback
        view = View(timeout=None)
        view.add_item(select)

        if self.TICKET_CREATION_MESSAGE_ID:
            try:
                message = await channel.fetch_message(self.TICKET_CREATION_MESSAGE_ID)
                await message.edit(view=view)
            except discord.NotFound:
                await self.send_new_ticket_message(channel, view)
        else:
            await self.send_new_ticket_message(channel, view)

    async def send_new_ticket_message(self, channel, view):
        message = await channel.send(
            "**Open a ticket!**\nSelect your issue from the dropdown:",
            view=view
        )
        self.TICKET_CREATION_MESSAGE_ID = message.id
        self.save_data()

    @commands.Cog.listener()
    async def on_ready(self):
        await self.reattach_ticket_views()

    async def reattach_ticket_views(self):
        for ticket_id, ticket in self.tickets.items():
            channel = self.bot.get_channel(ticket["channel_id"])
            if not channel:
                continue

            # Recreate buttons
            claim_btn = Button(
                style=discord.ButtonStyle.primary,
                label="Claim Ticket",
                custom_id=f"claim_{ticket_id}"
            )
            close_btn = Button(
                style=discord.ButtonStyle.danger,
                label="Close Ticket",
                custom_id=f"close_{ticket_id}"
            )

            async def claim_callback(interaction):
                await self.handle_claim(interaction, ticket_id)

            async def close_callback(interaction):
                await interaction.response.send_modal(
                    self.CloseTicketModal(self, ticket_id)
                )

            claim_btn.callback = claim_callback
            close_btn.callback = close_callback

            view = View(timeout=None)
            view.add_item(claim_btn)
            view.add_item(close_btn)
            
            self.bot.add_view(view, message_id=int(ticket_id))

    async def handle_claim(self, interaction, ticket_id):
        ticket = self.tickets.get(ticket_id)
        if not ticket:
            await interaction.response.send_message("Ticket not found!", ephemeral=True)
            return

        staff_role = interaction.guild.get_role(self.SUPPORT_ROLE_ID)
        if staff_role not in interaction.user.roles:
            await interaction.response.send_message("Missing permissions!", ephemeral=True)
            return

        ticket["claimed_by"] = interaction.user.id
        self.save_data()
        await interaction.response.send_message(
            f"Ticket claimed by {interaction.user.mention}!"
        )

    async def create_ticket(self, interaction, issue_type, modal=None):
        await interaction.response.defer(ephemeral=True)
        self.ticket_counter += 1
        ticket_id = str(self.ticket_counter)

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.get_role(self.SUPPORT_ROLE_ID): discord.PermissionOverwrite(
                read_messages=True, send_messages=True
            ),
        }

        category = interaction.guild.get_channel(self.TICKET_CATEGORY_ID)
        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{ticket_id}",
            category=category,
            overwrites=overwrites,
        )

        self.tickets[ticket_id] = {
            "channel_id": channel.id,
            "opened_by": interaction.user.id,
            "opened_at": datetime.datetime.now().isoformat(),
            "status": "open",
            "issue_type": issue_type,
            "claimed_by": None,
            "closed_by": None,
            "closed_at": None,
            "reason": None
        }
        self.save_data()

        # Send initial message
        embed = discord.Embed(
            title=f"Ticket #{ticket_id}",
            description=f"Thank you {interaction.user.mention}!\nSupport will be with you shortly.",
            color=discord.Color.green()
        )
        await channel.send(embed=embed)

        # Add action buttons
        view = View(timeout=None)
        claim_btn = Button(style=discord.ButtonStyle.primary, label="Claim", custom_id=f"claim_{ticket_id}")
        close_btn = Button(style=discord.ButtonStyle.danger, label="Close", custom_id=f"close_{ticket_id}")

        claim_btn.callback = lambda i: self.handle_claim(i, ticket_id)
        close_btn.callback = lambda i: i.response.send_modal(self.CloseTicketModal(self, ticket_id))
        
        view.add_item(claim_btn)
        view.add_item(close_btn)
        await channel.send("Ticket actions:", view=view)

        await interaction.followup.send(
            f"Ticket created: {channel.mention}", 
            ephemeral=True
        )

    async def close_ticket(self, interaction, ticket_id, reason):
        ticket = self.tickets.get(ticket_id)
        if not ticket:
            await interaction.response.send_message("Ticket not found!", ephemeral=True)
            return

        ticket.update({
            "closed_by": interaction.user.id,
            "closed_at": datetime.datetime.now().isoformat(),
            "reason": reason,
            "status": "closed"
        })
        self.save_data()

        # Delete channel
        channel = interaction.guild.get_channel(ticket["channel_id"])
        if channel:
            await channel.delete()

        # Create transcript
        transcript = await self.create_transcript(channel)
        transcript_url = await self.upload_transcript(ticket_id, transcript)
        
        # Send to transcripts channel
        logs_channel = interaction.guild.get_channel(self.TRANSCRIPTS_CHANNEL_ID)
        if logs_channel:
            embed = discord.Embed(
                title=f"Ticket #{ticket_id} Closed",
                description=f"**Reason:** {reason}\n[View Transcript]({transcript_url})",
                color=discord.Color.orange()
            )
            await logs_channel.send(embed=embed)

        await interaction.response.send_message("Ticket closed successfully!", ephemeral=True)

    async def create_transcript(self, channel):
        messages = []
        async for message in channel.history(oldest_first=True):
            messages.append({
                "author": str(message.author),
                "content": message.content,
                "timestamp": message.created_at.isoformat(),
                "embeds": [embed.to_dict() for embed in message.embeds]
            })
        
        template = env.from_string(open("transcript_template.html").read())
        return template.render(messages=messages)

    async def upload_transcript(self, ticket_id, content):
        headers = {
            "Authorization": f"Bearer {self.GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json"
        }
        data = {
            "message": f"Add transcript for ticket {ticket_id}",
            "content": base64.b64encode(content.encode()).decode(),
            "branch": "main"
        }
        
        response = requests.put(
            f"https://api.github.com/repos/{os.getenv('GITHUB_REPO')}/contents/transcripts/{ticket_id}.html",
            headers=headers,
            json=data
        )
        
        if response.status_code in [200, 201]:
            return f"https://github.com/{os.getenv('GITHUB_REPO')}/blob/main/transcripts/{ticket_id}.html"
        return None

async def setup(bot):
    await bot.add_cog(Tickets(bot))