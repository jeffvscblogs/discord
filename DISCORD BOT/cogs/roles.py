import discord
from discord.ext import commands
from discord import app_commands
import json
import os

class RoleManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.PSEUDO_MOD_ROLE_ID = int(os.getenv("PSEUDO_MOD_ROLE_ID"))
        self.MOD_ROLE_ID = int(os.getenv("MOD_ROLE_ID"))
        self.ADMIN_ROLE_ID = int(os.getenv("ADMIN_ROLE_ID"))
        
        # Load persistent lists
        self.pseudo_mod_list = self.load_list("pseudo_mods.json")
        self.mod_promotion_list = self.load_list("mod_promotion.json")

    def load_list(self, filename):
        try:
            with open(filename, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def save_list(self, filename, data):
        with open(filename, "w") as f:
            json.dump(data, f)

    @app_commands.command(name="add_pseudo_mod", description="Add user to pseudo-mod approval list")
    @app_commands.checks.has_role("Admin")
    async def add_pseudo_mod(self, interaction: discord.Interaction, member: discord.Member):
        if member.id not in self.pseudo_mod_list:
            self.pseudo_mod_list.append(member.id)
            self.save_list("pseudo_mods.json", self.pseudo_mod_list)
            await interaction.response.send_message(
                f"{member.mention} added to pseudo-mod approval list.", 
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"{member.mention} is already in the list.", 
                ephemeral=True
            )

    @app_commands.command(name="approve_pseudo_mods", description="Approve all pseudo-mods in the list")
    @app_commands.checks.has_role("Admin")
    async def approve_pseudo_mods(self, interaction: discord.Interaction):
        guild = interaction.guild
        role = guild.get_role(self.PSEUDO_MOD_ROLE_ID)
        
        if not role:
            await interaction.response.send_message("Pseudo-mod role not found!", ephemeral=True)
            return

        success = []
        failed = []
        
        for user_id in self.pseudo_mod_list:
            try:
                member = await guild.fetch_member(user_id)
                await member.add_roles(role)
                success.append(str(user_id))
                
                # Send rules embed
                embed = discord.Embed(title="Pseudo-MOD Rules", color=0x00ff00)
                # ... (your embed setup)
                
                try:
                    await member.send(embed=embed)
                except discord.Forbidden:
                    pass
                    
            except Exception as e:
                failed.append(f"{user_id} - {str(e)}")

        self.pseudo_mod_list = []
        self.save_list("pseudo_mods.json", self.pseudo_mod_list)

        report = f"Approved: {len(success)}\nFailed: {len(failed)}"
        await interaction.response.send_message(report, ephemeral=True)

    @app_commands.command(name="view_list", description="View approval lists")
    @app_commands.describe(list_name="The list to view (pseudo_mod or mod)")
    async def view_list(self, interaction: discord.Interaction, list_name: str):
        list_name = list_name.lower()
        if list_name == "pseudo_mod":
            data = self.pseudo_mod_list
        elif list_name == "mod":
            data = self.mod_promotion_list
        else:
            await interaction.response.send_message("Invalid list name!", ephemeral=True)
            return

        if not data:
            await interaction.response.send_message("List is empty!", ephemeral=True)
            return

        members = []
        for user_id in data:
            member = interaction.guild.get_member(user_id)
            members.append(f"{member.mention if member else f'Unknown ({user_id})'}")

        embed = discord.Embed(
            title=f"{list_name.replace('_', ' ').title()} List",
            description="\n".join(members),
            color=0x7289da
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @add_pseudo_mod.error
    @approve_pseudo_mods.error
    async def role_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingRole):
            await interaction.response.send_message("You don't have permission for this!", ephemeral=True)
        else:
            await interaction.response.send_message(f"Error: {str(error)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(RoleManagement(bot))
