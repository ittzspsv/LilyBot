from discord.ext import commands
from typing import Optional
from src.core.features.permissions.lily_permissions import app_permission, app_permission
from src.core.features.ticketing.controller.lily_ticketing_controller import LilyTicketingController
from src.core.utils.embeds.sLilyEmbed import simple_embed
import json
import discord, discord.app_commands as app_commands

class LilyTicketTool(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.controller: Optional[LilyTicketingController] = None

    @commands.Cog.listener()
    async def on_ready(self):
        if self.controller is not None:
            await self.controller.initialize_ticket_view(self.bot)
            print("[Ticket Tool Cog] Initialized")

    async def on_load(self):
         self.controller = LilyTicketingController(
              self.bot.db,
              self.bot.logging_controller
         )

    ticket = app_commands.Group(
        name="ticket",
        description="Lily Ticketing System Command Hierarchy!"
    )

    """
    @ticket.command(name='spawn', description='spawn in ticket processor')
    @app_permission(command_name="spawn_ticket", restrict=True)
    async def spawnticket(self, ctx: commands.Context):
        if self.controller is None:
            return

        if not ctx.message.attachments:
            await ctx.send("Please attach a .json Config")
            return

        for attachment in ctx.message.attachments:
            if attachment.filename.endswith('.json'):
                    content = await attachment.read()
                    json_data = json.loads(content.decode('utf-8'))
                    await self.controller.spawn_ticket(ctx, json_data)
                    await ctx.reply("Ticket has been spawned successfully!")
    """       
    @app_commands.guild_only()
    @ticket.command(name="close", description="Close a ticket thread")
    @app_permission(command_name="ticket_close")
    @app_commands.checks.cooldown(1, 20)
    async def CloseTicket(self, interaction: discord.Interaction, * ,reason: str="No reason provided"):
         if self.controller is not None:
            await self.controller.ticket_close(interaction, reason)
         
    @app_commands.guild_only()
    @ticket.command(name='rename', description='renames a ticket channel')
    @app_permission(command_name="ticket_rename")
    @app_commands.checks.cooldown(1, 10)
    async def rename_ticket(self, interaction: discord.Interaction, * ,name: str):
         if self.controller is not None:
            await self.controller.rename_ticket(interaction, name)

    @app_commands.guild_only()
    @ticket.command(name='add', description='adds a member to the ticket')
    @app_permission(command_name="ticket_add")
    @app_commands.checks.cooldown(1, 5)
    async def ticket_add(self, interaction: discord.Interaction, user: discord.Member):
         if self.controller is not None:
            await self.controller.ticket_add_user(interaction, user)


    @app_commands.guild_only()
    @ticket.command(name='remove', description='Remove a user from the ticket')
    @app_permission(command_name="ticket_remove")
    @app_commands.checks.cooldown(1, 5)
    async def ticket_remove(self, interaction: discord.Interaction, user: discord.Member):
        if self.controller is not None:
            await self.controller.ticket_remove_user(interaction, user)


    @app_commands.guild_only()
    @ticket.command(name='stats', description='Retrive your ticket stats')
    @app_permission(command_name="ticket_stats")
    @app_commands.checks.cooldown(1, 5)
    async def ticket_stats(self, interaction: discord.Interaction, staff: discord.Member | None=None):
        if self.controller is not None:
            member = staff if staff is not None else interaction.user
            assert isinstance(member, discord.Member)
            await self.controller.ticket_stats(interaction, member)


    @commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
    @app_permission(command_name="ticket_update")
    @ticket.command(name='update', description='Update the ticket config')
    async def ticket_update(
        self,
        interaction: discord.Interaction,
        message_id: str,
        attachment: discord.Attachment,
    ):
        if self.controller is None:
            await interaction.response.send_message(
                "Ticket controller is unavailable.",
                ephemeral=True,
            )
            return

        if interaction.guild is None:
            await interaction.response.send_message(
                embed=simple_embed("This command can only be used in a server.", 'cross'),
                ephemeral=True,
            )
            return

        if not attachment.filename.endswith(".json"):
            await interaction.response.send_message(
                embed=simple_embed("Please upload a `.json` configuration file.", 'cross'),
                ephemeral=True,
            )
            return

        try:
            content = await attachment.read()
            json_data = json.loads(content.decode("utf-8"))
        except json.JSONDecodeError:
            await interaction.response.send_message(
                embed=simple_embed("The uploaded file is not valid JSON.", 'cross'),
                ephemeral=True,
            )
            return
        except UnicodeDecodeError:
            await interaction.response.send_message(
                embed=simple_embed("The file must be UTF-8 encoded.", 'cross'),
                ephemeral=True,
            )
            return

        await self.bot.db.execute(
            """
            UPDATE ticket_views
            SET config_json = ?
            WHERE guild_id = ? AND message_id = ?
            """,
            (
                json.dumps(json_data),
                interaction.guild.id,
                int(message_id),
            ),
        )

        await interaction.response.send_message(
            embed=simple_embed("Ticket panel configuration has been updated."),
            ephemeral=True,
        )


async def setup(bot):
    cog = LilyTicketTool(bot)
    await bot.add_cog(cog)

    if hasattr(cog, "on_load"):
        await cog.on_load()