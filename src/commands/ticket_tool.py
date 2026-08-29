from discord.ext import commands
from typing import Optional
from src.core.features.permissions.lily_permissions import app_permission, permission
from src.core.utils.embeds.sLilyEmbed import simple_embed
import json
import discord, discord.app_commands as app_commands

from src.core.features.ticketing.controller.lily_ticketing_controller import *
from src.core.features.ticketing.components.LilyTicketToolComponents import TicketList

import logging

logger = logging.getLogger("lily")

class LilyTicketTool(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        await initialize_ticket_view(self.bot)
        print("[Ticket Tool Cog] Initialized")

    async def on_load(self):
        ...

    ticket = app_commands.Group(
        name="ticket",
        description="Lily Ticketing System Command Hierarchy!"
    )

    @commands.command(name='ticket_spawn', description='spawn in ticket processor')
    @permission(command_name="ticket_spawn", restrict=True)
    async def spawnticket(self, ctx: commands.Context):
        if not ctx.message.attachments:
            await ctx.send("Please attach a .json Config")
            return

        for attachment in ctx.message.attachments:
            if attachment.filename.endswith('.json'):
                    content = await attachment.read()
                    json_data = json.loads(content.decode('utf-8'))
                    await spawn_ticket(ctx, json_data)
                    await ctx.reply("Ticket has been spawned successfully!")

    @app_commands.guild_only()
    @ticket.command(name="close", description="Close a ticket thread")
    @app_permission(command_name="ticket_close")
    @app_commands.checks.cooldown(1, 20)
    async def CloseTicket(self, interaction: discord.Interaction, * ,reason: str="No reason provided"):
        await ticket_close(interaction, reason)

    @app_commands.guild_only()
    @ticket.command(name='rename', description='renames a ticket channel')
    @app_permission(command_name="ticket_rename")
    @app_commands.checks.cooldown(1, 10)
    async def rename_ticket(self, interaction: discord.Interaction, * ,name: str):
        await rename_ticket(interaction, name)

    @app_commands.guild_only()
    @ticket.command(name='add', description='adds a member to the ticket')
    @app_permission(command_name="ticket_add")
    @app_commands.checks.cooldown(1, 5)
    async def ticket_add(self, interaction: discord.Interaction, user: discord.Member):
        await ticket_add_user(interaction, user)

    @app_commands.guild_only()
    @ticket.command(name='remove', description='Remove a user from the ticket')
    @app_permission(command_name="ticket_remove")
    @app_commands.checks.cooldown(1, 5)
    async def ticket_remove(self, interaction: discord.Interaction, user: discord.Member):
        await ticket_remove_user(interaction, user)

    @app_commands.guild_only()
    @ticket.command(name='stats', description='Retrive your ticket stats')
    @app_permission(command_name="ticket_stats")
    @app_commands.checks.cooldown(1, 5)
    async def ticket_stats(self, interaction: discord.Interaction, staff: discord.Member | None=None):
        member = staff if staff is not None else interaction.user
        assert isinstance(member, discord.Member)
        await ticket_stats(interaction, member)

    @commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
    @app_permission(command_name="ticket_update")
    @ticket.command(name='update', description='Update the ticket config')
    async def ticket_update(
        self,
        interaction: discord.Interaction,
        message_id: str,
        attachment: discord.Attachment,
    ):
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


    @commands.cooldown(rate=1, per=5, type=commands.BucketType.user)
    @app_permission(command_name="ticket_retrieve")
    @app_commands.guild_only()
    @ticket.command(name="retrieve", description="Retrieve all tickets (can be filtered)")
    async def ticket_retrieve(self, interaction: discord.Interaction):
        assert interaction.guild is not None

        ticket_results = await self.bot.db.get_ticket_logs(guild_id=interaction.guild.id)
        ticket_types = await self.bot.db.get_ticket_types(interaction.guild.id)
        guild_avatar = interaction.guild.icon.url if interaction.guild.icon else None
        try:
            await interaction.response.send_message(
                view=TicketList(ticket_results, guild_avatar=guild_avatar, ticket_types=ticket_types),
                ephemeral=True
            )
        except Exception:
            logger.exception("Failed to send ticket list view")



async def setup(bot):
    cog = LilyTicketTool(bot)
    await bot.add_cog(cog)

    if hasattr(cog, "on_load"):
        await cog.on_load()