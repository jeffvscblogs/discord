import discord
from discord.ext import commands
from discord.ui import Select, Button, View, Modal, TextInput
import json
import os
import base64
import requests
import datetime
import asyncio
import aiohttp
import io
from jinja2 import Environment, BaseLoader

# Configure Jinja2 environment
def replace_mentions_filter(content, users):
    for user_id, username in users.items():
        content = content.replace(f"<@{user_id}>", f"@{username}")
        content = content.replace(f"<@!{user_id}>", f"@{username}")
    return content

env = Environment(loader=BaseLoader)
env.filters['replace_mentions'] = replace_mentions_filter

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tickets = {}
        self.ticket_counter = 0
        self.TICKET_CREATION_MESSAGE_ID = None
        
        # Configuration from environment
        self.TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID"))
        self.TRANSCRIPTS_CHANNEL_ID = int(os.getenv("TRANSCRIPTS_CHANNEL_ID"))
        self.SUPPORT_ROLE_ID = int(os.getenv("SUPPORT_ROLE_ID"))
        self.GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
        self.GITHUB_REPO = os.getenv("GITHUB_REPO")
        self.TICKET_CREATION_CHANNEL_ID = int(os.getenv("TICKET_CREATION_CHANNEL_ID"))
        
        # Persistent data files
        self.TICKETS_FILE = "tickets.json"
        self.TICKET_COUNTER_FILE = "ticket_counter.txt"
        self.TICKET_MESSAGE_FILE = "ticket_message_id.txt"
        
        self.load_data()
        self.bot.loop.create_task(self.setup_ticket_creation_message())

    # Data management
    def load_data(self):
        try:
            # Load ticket counter
            if os.path.exists(self.TICKET_COUNTER_FILE):
                with open(self.TICKET_COUNTER_FILE, "r") as f:
                    self.ticket_counter = int(f.read().strip())
            
            # Load ticket message ID
            if os.path.exists(self.TICKET_MESSAGE_FILE):
                with open(self.TICKET_MESSAGE_FILE, "r") as f:
                    self.TICKET_CREATION_MESSAGE_ID = int(f.read().strip())
            
            # Load active tickets
            if os.path.exists(self.TICKETS_FILE):
                with open(self.TICKETS_FILE, "r") as f:
                    self.tickets = json.load(f)
                    
        except Exception as e:
            self.bot.logger.error(f"Error loading ticket data: {e}")

    def save_data(self):
        try:
            with open(self.TICKET_COUNTER_FILE, "w") as f:
                f.write(str(self.ticket_counter))
            
            with open(self.TICKET_MESSAGE_FILE, "w") as f:
                if self.TICKET_CREATION_MESSAGE_ID:
                    f.write(str(self.TICKET_CREATION_MESSAGE_ID))
            
            with open(self.TICKETS_FILE, "w") as f:
                json.dump(self.tickets, f, indent=4)
                
        except Exception as e:
            self.bot.logger.error(f"Error saving ticket data: {e}")

    # Ticket creation setup
    async def setup_ticket_creation_message(self):
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(self.TICKET_CREATION_CHANNEL_ID)
        
        if not channel:
            self.bot.logger.error("Ticket creation channel not found!")
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
            try:
                if select.values[0] == "apply_for_staff":
                    await interaction.response.send_modal(StaffApplicationModal(self))
                else:
                    await self.create_ticket(interaction, select.values[0])
            except Exception as e:
                self.bot.logger.error(f"Ticket creation error: {e}")
                await interaction.response.send_message("Error creating ticket!", ephemeral=True)

        select.callback = select_callback
        view = View(timeout=None)
        view.add_item(select)

        # Update or create message
        try:
            if self.TICKET_CREATION_MESSAGE_ID:
                message = await channel.fetch_message(self.TICKET_CREATION_MESSAGE_ID)
                await message.edit(view=view)
            else:
                message = await channel.send(
                    "**Open a Ticket**\nSelect your issue below:",
                    view=view
                )
                self.TICKET_CREATION_MESSAGE_ID = message.id
                self.save_data()
        except discord.NotFound:
            self.bot.logger.warning("Ticket message not found, creating new one")
            message = await channel.send(
                "**Open a Ticket**\nSelect your issue below:",
                view=view
            )
            self.TICKET_CREATION_MESSAGE_ID = message.id
            self.save_data()

    # Ticket management
    class StaffApplicationModal(Modal, title="Staff Application"):
        def __init__(self, cog):
            super().__init__()
            self.cog = cog
            self.role = TextInput(label="Applying for which role?", required=True)
            self.studying = TextInput(label="Current area of study?", required=True)
            self.availability = TextInput(label="Available hours per day?", required=True)
            self.experience = TextInput(label="Relevant experience?", style=discord.TextStyle.long)

        async def on_submit(self, interaction: discord.Interaction):
            await self.cog.create_ticket(
                interaction,
                "staff_application",
                application_data={
                    "role": self.role.value,
                    "studying": self.studying.value,
                    "availability": self.availability.value,
                    "experience": self.experience.value
                }
            )

    class CloseTicketModal(Modal, title="Close Ticket"):
        def __init__(self, cog, ticket_id):
            super().__init__()
            self.cog = cog
            self.ticket_id = ticket_id
            self.reason = TextInput(
                label="Closing Reason",
                style=discord.TextStyle.long,
                required=True
            )

        async def on_submit(self, interaction: discord.Interaction):
            await self.cog.close_ticket(interaction, self.ticket_id, self.reason.value)

    async def create_ticket(self, interaction, ticket_type, application_data=None):
        try:
            await interaction.response.defer(ephemeral=True)
            self.ticket_counter += 1
            ticket_id = str(self.ticket_counter)
            
            # Create permission overwrites
            guild = interaction.guild
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    attach_files=True
                ),
                guild.get_role(self.SUPPORT_ROLE_ID): discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    manage_messages=True
                )
            }

            # Create ticket channel
            category = guild.get_channel(self.TICKET_CATEGORY_ID)
            channel = await guild.create_text_channel(
                name=f"ticket-{ticket_id}",
                category=category,
                overwrites=overwrites
            )

            # Store ticket data
            self.tickets[ticket_id] = {
                "channel_id": channel.id,
                "creator": interaction.user.id,
                "created_at": datetime.datetime.now().isoformat(),
                "type": ticket_type,
                "status": "open",
                "claimed_by": None,
                "closed_by": None,
                "closed_at": None,
                "application_data": application_data
            }
            self.save_data()

            # Send initial message
            embed = discord.Embed(
                title=f"Ticket #{ticket_id}",
                description=f"Hello {interaction.user.mention}! Support will be with you shortly.",
                color=discord.Color.green()
            )
            await channel.send(embed=embed)

            # Add application data if exists
            if application_data:
                app_embed = discord.Embed(
                    title="Staff Application Details",
                    color=discord.Color.blue()
                )
                for key, value in application_data.items():
                    app_embed.add_field(name=key.title(), value=value, inline=False)
                await channel.send(embed=app_embed)

            # Add action buttons
            view = View(timeout=None)
            
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
            
            view.add_item(claim_btn)
            view.add_item(close_btn)
            
            await channel.send("Ticket Actions:", view=view)
            self.bot.add_view(view, message_id=int(ticket_id))

            await interaction.followup.send(
                f"Ticket created: {channel.mention}",
                ephemeral=True
            )

        except Exception as e:
            self.bot.logger.error(f"Ticket creation failed: {e}")
            await interaction.followup.send(
                "Failed to create ticket. Please contact staff.",
                ephemeral=True
            )

    async def handle_claim(self, interaction, ticket_id):
        try:
            ticket = self.tickets.get(ticket_id)
            if not ticket:
                return await interaction.response.send_message(
                    "Ticket not found!",
                    ephemeral=True
                )

            support_role = interaction.guild.get_role(self.SUPPORT_ROLE_ID)
            if support_role not in interaction.user.roles:
                return await interaction.response.send_message(
                    "You don't have permission to claim tickets!",
                    ephemeral=True
                )

            ticket["claimed_by"] = interaction.user.id
            self.save_data()
            
            await interaction.response.send_message(
                f"Ticket claimed by {interaction.user.mention}",
                ephemeral=False
            )
            
        except Exception as e:
            self.bot.logger.error(f"Ticket claim error: {e}")
            await interaction.response.send_message(
                "Failed to claim ticket.",
                ephemeral=True
            )

    async def close_ticket(self, interaction, ticket_id, reason):
        try:
            await interaction.response.defer(ephemeral=True)
            ticket = self.tickets.get(ticket_id)
            
            if not ticket:
                return await interaction.followup.send(
                    "Ticket not found!",
                    ephemeral=True
                )

            # Update ticket data
            ticket.update({
                "closed_by": interaction.user.id,
                "closed_at": datetime.datetime.now().isoformat(),
                "status": "closed",
                "close_reason": reason
            })
            self.save_data()

            # Generate transcript
            transcript = await self.generate_transcript(ticket_id)
            transcript_url = await self.upload_transcript(ticket_id, transcript)
            
            # Send to transcripts channel
            logs_channel = self.bot.get_channel(self.TRANSCRIPTS_CHANNEL_ID)
            if logs_channel:
                embed = discord.Embed(
                    title=f"Ticket #{ticket_id} Closed",
                    description=f"**Reason:** {reason}",
                    color=discord.Color.orange()
                )
                embed.add_field(name="Creator", value=f"<@{ticket['creator']}>")
                embed.add_field(name="Closer", value=interaction.user.mention)
                if transcript_url:
                    embed.add_field(name="Transcript", value=transcript_url, inline=False)
                await logs_channel.send(embed=embed)

            # Delete ticket channel
            channel = self.bot.get_channel(ticket["channel_id"])
            if channel:
                await channel.delete()

            await interaction.followup.send(
                "Ticket closed successfully!",
                ephemeral=True
            )

        except Exception as e:
            self.bot.logger.error(f"Ticket closure error: {e}")
            await interaction.followup.send(
                "Failed to close ticket. Please contact admin.",
                ephemeral=True
            )

    async def generate_transcript(self, ticket_id):
        try:
            ticket = self.tickets[ticket_id]
            channel = self.bot.get_channel(ticket["channel_id"])
            
            if not channel:
                return None

            messages = []
            users = {}
            async for message in channel.history(oldest_first=True):
                users[str(message.author.id)] = message.author.name
                messages.append({
                    "author": message.author.name,
                    "content": message.content,
                    "timestamp": message.created_at.strftime("%Y-%m-%d %H:%M"),
                    "embeds": [embed.to_dict() for embed in message.embeds]
                })

            template = env.from_string(open("transcript_template.html").read())
            return template.render(
                ticket_id=ticket_id,
                messages=messages,
                users=users
            )
            
        except Exception as e:
            self.bot.logger.error(f"Transcript generation failed: {e}")
            return None

    async def upload_transcript(self, ticket_id, content):
        if not content or not self.GITHUB_TOKEN:
            return None

        try:
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
                f"https://api.github.com/repos/{self.GITHUB_REPO}/contents/transcripts/{ticket_id}.html",
                headers=headers,
                json=data
            )

            if response.status_code in [200, 201]:
                return f"https://github.com/{self.GITHUB_REPO}/blob/main/transcripts/{ticket_id}.html"
            return None
            
        except Exception as e:
            self.bot.logger.error(f"GitHub upload failed: {e}")
            return None

    @commands.Cog.listener()
    async def on_ready(self):
        await self.reattach_ticket_views()

    async def reattach_ticket_views(self):
        for ticket_id in self.tickets:
            channel = self.bot.get_channel(self.tickets[ticket_id]["channel_id"])
            if not channel:
                continue

            view = View(timeout=None)
            
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
                
            claim_btn.callback = claim_callback
            close_btn.callback = close_callback
            
            view.add_item(claim_btn)
            view.add_item(close_btn)
            
            self.bot.add_view(view, message_id=int(ticket_id))

async def setup(bot):
    await bot.add_cog(Tickets(bot))
