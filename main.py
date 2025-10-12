import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="?", intents=intents)

# -----------------------------
# SAY COMMAND (from your code)
# -----------------------------
@bot.command()
async def say(ctx, *, message):
    await ctx.message.delete()
    await ctx.send(message)

# -----------------------------
# LOCK COMMAND
# -----------------------------
@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    """Locks the current channel for @everyone"""
    overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
    overwrite.send_messages = False
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
    await ctx.send(embed=discord.Embed(
        title="🔒 Channel Locked",
        description=f"{ctx.author.mention} has locked this channel.",
        color=discord.Color.red()
    ))

# -----------------------------
# TICKET SYSTEM
# -----------------------------
class TicketDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="General Support", emoji="💬", description="Open a general help ticket"),
            discord.SelectOption(label="Report Issue", emoji="⚠️", description="Report a bug or issue"),
            discord.SelectOption(label="Apply for Role", emoji="📝", description="Start a staff or role application")
        ]
        super().__init__(
            placeholder="🎟️ Select a ticket type...",
            min_values=1,
            max_values=1,
            options=options
         )
        title="🎟️ Ticket Created",
        description=f"{interaction.user.mention}, please describe your issue or request below.",
        color=discord.Color.green()
        await
    ticket_channel.send(embed=embed)
        await interaction.response.send_message(f"✅ Your ticket has been created: {ticket_channel.mention}", ephemeral=True)

        class TicketDropdownView(discord.ui.View):
        def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketDropdown())

        @bot.command()
        @commands.has_permissions(manage_channels=True)
        async def ticketpanel(ctx):
        """Creates a dropdown ticket panel"""
        embed = discord.Embed(
        title="🎫 Support Ticket Panel",
        description="Select the type of ticket you want to open below:",
        color=discord.Color.blue()
        )
        await ctx.send(embed=embed, view=TicketDropdownView())

        # -----------------------------
        # BOT READY EVENT
        # -----------------------------
        @bot.event
        async def on_ready():
        print(f"✅ Logged in as {bot.user}")
        try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
        except Exception as e:
        print(f"Slash sync error: {e}")

        # -----------------------------
        # RUN BOT
        # -----------------------------
        bot.run("MTQyNDQ1NjUzMTc1MTIwNjk5Mg.GUYIOz.Li6GgojZdWPrpK6v64iMW3SPn7qF8nds8NsCAs")
