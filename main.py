# bot.py
import discord
from discord import app_commands
from discord.ext import commands
import os
import json
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional

load_dotenv()  # loads .env

TOKEN = os.getenv("TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID")) if os.getenv("GUILD_ID") else None
SUPPORT_ROLE_NAME = os.getenv("SUPPORT_ROLE_NAME", "Support")
VERIFY_ROLE_NAME = os.getenv("VERIFY_ROLE_NAME", "Member")
TICKETS_FOLDER = os.getenv("TICKETS_FOLDER", "tickets")

# Basic persistence for tickets
Path(TICKETS_FOLDER).mkdir(parents=True, exist_ok=True)
TICKETS_FILE = Path(TICKETS_FOLDER) / "tickets.json"


def load_tickets():
    if not TICKETS_FILE.exists():
        data = {
            "next_id": 1,
            "open": {}
        }  # open: ticket_id -> {guild_id, channel_id, owner_id}
        TICKETS_FILE.write_text(json.dumps(data))
        return data
    return json.loads(TICKETS_FILE.read_text())


def save_tickets(data):
    TICKETS_FILE.write_text(json.dumps(data, indent=2))


tickets_db = load_tickets()

# Intents
intents = discord.Intents.default()
intents.message_content = False
intents.guilds = True
intents.members = True  # needed to give roles and set channel perms

# Bot & tree (slash commands)
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree


# Utility: check for admin/ManageGuild or ban_members
def is_moderator(interaction: discord.Interaction) -> bool:
    if interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.ban_members:
        return True
    return False


# ---------- Views (buttons) ----------
class VerifyView(discord.ui.View):

    def __init__(self, role_id: int):
        super().__init__(timeout=None)
        self.role_id = role_id

    @discord.ui.button(label="Verify",
                       style=discord.ButtonStyle.success,
                       custom_id="verify_button")
    async def verify_button(self, interaction: discord.Interaction,
                            button: discord.ui.Button):
        guild = interaction.guild
        role = guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message(
                "Verification role not found. Contact an admin.",
                ephemeral=True)
            return
        member = interaction.user
        if role in member.roles:
            await interaction.response.send_message(
                "You are already verified.", ephemeral=True)
            return
        try:
            await member.add_roles(role, reason="User verified via panel")
            await interaction.response.send_message(
                f"✅ You have been given the **{role.name}** role.",
                ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to assign that role.", ephemeral=True)


class TicketCreateView(discord.ui.View):

    def __init__(self, support_role_id: Optional[int]):
        super().__init__(timeout=None)
        self.support_role_id = support_role_id

    @discord.ui.button(label="Create Ticket",
                       style=discord.ButtonStyle.primary,
                       custom_id="create_ticket")
    async def create_ticket(self, interaction: discord.Interaction,
                            button: discord.ui.Button):
        guild = interaction.guild
        author = interaction.user

        # Create a new ticket id
        global tickets_db
        ticket_id = tickets_db["next_id"]
        tickets_db["next_id"] += 1

        # Channel name and permissions
        channel_name = f"ticket-{ticket_id}-{author.name}".lower().replace(
            " ", "-")
        overwrites = {
            guild.default_role:
            discord.PermissionOverwrite(view_channel=False),
            author:
            discord.PermissionOverwrite(view_channel=True,
                                        send_messages=True,
                                        read_messages=True),
            guild.me:
            discord.PermissionOverwrite(view_channel=True,
                                        send_messages=True,
                                        read_messages=True)
        }

        if self.support_role_id:
            role = guild.get_role(self.support_role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_messages=True)

        # Create channel under same category as the message if possible, otherwise top-level
        parent = interaction.channel.category if isinstance(
            interaction.channel,
            discord.TextChannel) and interaction.channel.category else None
        try:
            chan = await guild.create_text_channel(channel_name,
                                                   overwrites=overwrites,
                                                   category=parent,
                                                   reason="Ticket created")
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to create channels.", ephemeral=True)
            return
        # Save ticket record
        tickets_db["open"][str(ticket_id)] = {
            "guild_id": guild.id,
            "channel_id": chan.id,
            "owner_id": author.id
        }
        save_tickets(tickets_db)

        # Send initial message with a close button
        view = TicketCloseView(ticket_id)
        await chan.send(
            f"Hello {author.mention}! A staff member will be with you shortly. Ticket ID: **{ticket_id}**",
            view=view)
        await interaction.response.send_message(
            f"✅ Created ticket: {chan.mention}", ephemeral=True)


class TicketCloseView(discord.ui.View):

    def __init__(self, ticket_id):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id

    @discord.ui.button(label="Close Ticket",
                       style=discord.ButtonStyle.danger,
                       custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction,
                           button: discord.ui.Button):
        # Only staff or ticket owner can close
        guild = interaction.guild
        data = tickets_db["open"].get(str(self.ticket_id))
        if not data:
            await interaction.response.send_message(
                "Ticket not found or already closed.", ephemeral=True)
            return

        owner_id = data.get("owner_id")
        support_role = discord.utils.get(guild.roles, name=SUPPORT_ROLE_NAME)
        can_close = False
        if interaction.user.id == owner_id:
            can_close = True
        elif support_role and support_role in interaction.user.roles:
            can_close = True
        elif interaction.user.guild_permissions.manage_guild:
            can_close = True

        if not can_close:
            await interaction.response.send_message(
                "Only the ticket owner, support staff, or an admin may close this ticket.",
                ephemeral=True)
            return

        channel = interaction.channel
        await channel.send("Ticket will be closed in 5 seconds...")
        await channel.edit(reason="Ticket closed",
                           name=f"closed-{channel.name}",
                           topic="Closed ticket")
        # remove from db
        tickets_db["open"].pop(str(self.ticket_id), None)
        save_tickets(tickets_db)
        # Optionally, archive or delete channel after a delay. We'll just lock it:
        try:
            await channel.set_permissions(interaction.user,
                                          send_messages=False,
                                          view_channel=False)
            await channel.set_permissions(guild.me,
                                          send_messages=False,
                                          view_channel=True)
        except Exception:
            pass
        await interaction.response.send_message("Ticket closed.",
                                                ephemeral=True)


# ---------- Commands & Events ----------


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    # Sync commands - if GUILD_ID provided, sync to that guild for faster updates during development
    if GUILD_ID:
        guild = discord.Object(id=GUILD_ID)
        await tree.sync(guild=guild)
        print(f"Synced commands to guild {GUILD_ID}")
    else:
        await tree.sync()
        print("Synced global commands")
    print("Bot ready.")


# ---------- Moderation Slash Commands ----------
@tree.command(name="ban",
              description="Ban a member",
              guild=discord.Object(id=GUILD_ID) if GUILD_ID else None)
@app_commands.describe(member="Member to ban", reason="Optional reason")
async def ban(interaction: discord.Interaction,
              member: discord.Member,
              reason: Optional[str] = None):
    # Permission check
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message(
            "You don't have permission to ban members.", ephemeral=True)
        return
    try:
        await member.ban(reason=f"{reason} — by {interaction.user}",
                         delete_message_days=0)
        await interaction.response.send_message(
            f"✅ Banned {member.mention}. Reason: {reason or 'No reason provided.'}"
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "I don't have permission to ban that member.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Failed to ban: {e}",
                                                ephemeral=True)


@tree.command(name="kick",
              description="Kick a member",
              guild=discord.Object(id=GUILD_ID) if GUILD_ID else None)
@app_commands.describe(member="Member to kick", reason="Optional reason")
async def kick(interaction: discord.Interaction,
               member: discord.Member,
               reason: Optional[str] = None):
    if not interaction.user.guild_permissions.kick_members:
        await interaction.response.send_message(
            "You don't have permission to kick members.", ephemeral=True)
        return
    try:
        await member.kick(reason=f"{reason} — by {interaction.user}")
        await interaction.response.send_message(
            f"✅ Kicked {member.mention}. Reason: {reason or 'No reason provided.'}"
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "I don't have permission to kick that member.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Failed to kick: {e}",
                                                ephemeral=True)


# ---------- Admin helpers to create panels ----------
@tree.command(name="create_verify_panel",
              description="Create a verification panel (admin only)",
              guild=discord.Object(id=GUILD_ID) if GUILD_ID else None)
async def create_verify_panel(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "You must be a server admin to use this.", ephemeral=True)
        return

    # Ensure role exists
    role = discord.utils.get(interaction.guild.roles, name=VERIFY_ROLE_NAME)
    if not role:
        try:
            role = await interaction.guild.create_role(
                name=VERIFY_ROLE_NAME, reason="Create verify role")
        except discord.Forbidden:
            await interaction.response.send_message(
                "I cannot create the verification role; please create a role named '{VERIFY_ROLE_NAME}' or give me permissions.",
                ephemeral=True)
            return

    view = VerifyView(role.id)
    embed = discord.Embed(
        title="Server Verification",
        description="Click **Verify** to get access to the server.",
        color=discord.Color.green())
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("Verification panel created.",
                                            ephemeral=True)


@tree.command(name="create_ticket_panel",
              description="Create a ticket panel (admin only)",
              guild=discord.Object(id=GUILD_ID) if GUILD_ID else None)
async def create_ticket_panel(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "You must be a server admin to use this.", ephemeral=True)
        return

    # find support role
    role = discord.utils.get(interaction.guild.roles, name=SUPPORT_ROLE_NAME)
    support_role_id = role.id if role else None

    view = TicketCreateView(support_role_id)
    embed = discord.Embed(
        title="Support Tickets",
        description=
        "Click **Create Ticket** to open a private support channel.",
        color=discord.Color.blue())
    if role:
        embed.add_field(name="Support Role", value=role.mention, inline=False)
    else:
        embed.add_field(
            name="Support Role",
            value=
            f"No role named '{SUPPORT_ROLE_NAME}' found. Create one for staff access",
            inline=False)

    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("Ticket panel created.",
                                            ephemeral=True)


# ---------- Optional: Admin command to close a ticket by id ----------
@tree.command(name="close_ticket",
              description="Close an open ticket by ID (staff or owner)",
              guild=discord.Object(id=GUILD_ID) if GUILD_ID else None)
@app_commands.describe(ticket_id="ID of the ticket to close")
async def close_ticket(interaction: discord.Interaction, ticket_id: int):
    record = tickets_db["open"].get(str(ticket_id))
    if not record:
        await interaction.response.send_message("Ticket not found.",
                                                ephemeral=True)
        return
    guild = interaction.guild
    channel = guild.get_channel(record["channel_id"])
    if not channel:
        await interaction.response.send_message("Ticket channel not found.",
                                                ephemeral=True)
        # cleanup
        tickets_db["open"].pop(str(ticket_id), None)
        save_tickets(tickets_db)
        return

    owner_id = record["owner_id"]
    support_role = discord.utils.get(guild.roles, name=SUPPORT_ROLE_NAME)
    if interaction.user.id != owner_id and (
            not support_role or support_role not in interaction.user.roles
    ) and not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message(
            "You don't have permission to close this ticket.", ephemeral=True)
        return

    # Lock and rename channel
    try:
        await channel.edit(name=f"closed-{channel.name}",
                           topic="Closed ticket",
                           reason="Ticket closed via command")
        tickets_db["open"].pop(str(ticket_id), None)
        save_tickets(tickets_db)
        await interaction.response.send_message(f"Ticket {ticket_id} closed.",
                                                ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Failed to close ticket: {e}",
                                                ephemeral=True)


# ---------- Basic error handling ----------
@bot.event
async def on_app_command_error(interaction: discord.Interaction,
                               error: app_commands.AppCommandError):
    # Provide sensible messages for common permission errors
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "You don't have permission to run this command.", ephemeral=True)
    else:
        try:
            await interaction.response.send_message(
                f"An error occurred: {error}", ephemeral=True)
        except Exception:
            pass
        print("Command error:", error)


# ---------- Run ----------
if __name__ == "__main__":
    if not TOKEN:
        print("Please set TOKEN in your environment (.env).")
    else:
        from flask import Flask
        from threading import Thread

        app = Flask('')

        @app.route('/')
        def home():
            return "Bot is running!"

        def run():
            app.run(host='0.0.0.0', port=8080)

        Thread(target=run).start()
        bot.run(TOKEN)
