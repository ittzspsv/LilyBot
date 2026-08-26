from __future__ import annotations

import asyncio
import io
import json

import discord
from discord.ext import commands

from typing import List, Dict, Any, TYPE_CHECKING, cast

from src.core.configs.sBotDetails import img
from src.core.utils.embeds.sLilyEmbed import (
    ParseAdvancedEmbed,
    simple_embed,
)

from ..classes.ticketing_classes import (
    DatabaseAccess,
)
from ..components.LilyTicketToolComponents import (
    TicketComponentEmbed,
    TicketOpenerComponent,
    TicketSelectComponent,
    TicketLogComponent,
    TicketLogDirectMessage,
    build_ticket_summary
)

from ..transcript import transcript

if TYPE_CHECKING:
    from src.lily import Lily

async def initialize_ticket_view(bot):
    try:
        _bot: Lily = cast(Lily, bot)
        bot_db = _bot.db
        logging_controller = _bot.logging_controller

        assert bot_db is not None
        assert logging_controller is not None
        panels = await bot_db.get_ticket_views()

        if not panels:
            print("[InitializeTicketView] No ticket panels found.")
            return

        for panel in panels:
            try:
                guild_id, channel_id, message_id, config_json = panel

                config = json.loads(config_json)

                if not config:
                    continue

                channel = bot.get_channel(channel_id)

                if not channel:
                    try:
                        channel = await bot.fetch_channel(channel_id)
                    except (discord.NotFound, discord.Forbidden):
                        print(f"[InitializeTicketView] Missing channel {channel_id}")
                        continue

                selector_view = TicketSelectComponent(config, DatabaseAccess(bot_db, logging_controller))
                bot.add_view(selector_view)

                try:
                    if message_id:
                        message = await channel.fetch_message(message_id)
                        await message.edit(
                            content=None,
                            embeds=[],
                            view=selector_view
                        )

                    else:
                        message = await channel.send(
                            view=selector_view
                        )

                        await bot_db.save_ticket_view(
                            guild_id=guild_id,
                            channel_id=channel_id,
                            message_id=message.id,
                            config=config
                        )

                except (discord.NotFound, discord.Forbidden):
                    print(f"[InitializeTicketView] Panel message missing in {channel_id}")
                    continue

                try:
                    tickets = await bot_db.get_guild_tickets(guild_id)

                    for ticket_id, _, submission_json, ticket_message_id, ticket_details_message_id in tickets:
                        view = TicketComponentEmbed(
                            ticket_id,
                            json.loads(submission_json),
                            config,
                            DatabaseAccess(bot_db, logging_controller)
                        )

                        opener_view = TicketOpenerComponent(
                            json.loads(submission_json),
                            config,
                            ticket_id,
                            DatabaseAccess(bot_db, logging_controller)
                        )

                        bot.add_view(
                            view,
                            message_id=ticket_details_message_id
                        )

                        bot.add_view(
                            opener_view,
                            message_id=ticket_message_id
                        )

                except Exception as e:
                    print(f"[Ticket Component Restore ERROR] {e}")

                await asyncio.sleep(1)

            except Exception as e:
                print(f"[TicketPanel Restore ERROR] {e}")
                continue

    except Exception as e:
        print(f"[InitializeTicketView ERROR] {e}")

async def spawn_ticket(ctx: commands.Context, json_data: dict) -> None:
    if ctx.guild is None:
        return

    bot_db = cast(Lily, ctx.bot).db
    logging_controller = cast(Lily, ctx.bot).logging_controller
    assert bot_db is not None
    assert logging_controller is not None

    try:
        content, embeds = ParseAdvancedEmbed(
            json_data["EmbedConfigs"]["TicketPanelEmbed"]
        )

        if not isinstance(embeds, list):
            embeds = [embeds]

        channel_id = json_data["BasicConfigurations"]["TicketPanelSpawnChannel"]

        channel_obj = (
            ctx.guild.get_channel(channel_id)
            or await ctx.guild.fetch_channel(channel_id)
        )

        if not isinstance(channel_obj, discord.TextChannel):
            raise RuntimeError("Invalid ticket panel channel.")


        selector_view = TicketSelectComponent(json_data, DatabaseAccess(bot_db, logging_controller))

        ctx.bot.add_view(selector_view)


        message_obj = await channel_obj.send(
            view=selector_view
        )

        await bot_db.save_ticket_view(
            guild_id=ctx.guild.id,
            channel_id=channel_obj.id,
            message_id=message_obj.id,
            config=json_data
        )


    except Exception as e:
        print(f"[SPAWN TICKET ERROR] {e}")

        await ctx.reply(
            "Failed to spawn ticket panel due to an internal error."
        )

async def c_ticket_log_action_channel(interaction: discord.Interaction,opened_user_id: int,ticket_type: str, logs_channel: discord.TextChannel, transcripts_file, transcript_file_name: str ,reason: str="No reason provided!") -> int:
    view = TicketLogComponent(
        opened_user_id,
        interaction.user.id,
        ticket_type,
        reason,
        transcript_file_name
    )

    try:
        message: discord.Message = await logs_channel.send(
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
            file=transcripts_file
        )
        
        return message.id
    except Exception as e:
        print(f"Exception [TicketLogAction] {e}")
        return 0

async def rename_ticket(interaction: discord.Interaction, name: str):
    if not isinstance(interaction.channel, discord.TextChannel):
        return
    bot_db = cast(Lily, interaction.client).db
    assert bot_db is not None

    owner = await bot_db.get_ticket_owner(interaction.channel.id)
    if owner:
        await interaction.channel.edit(name=name.replace(" ", "_"), reason=f"Ticket renamed by {interaction.user}")
        await interaction.response.send_message(embed=simple_embed("Ticket renamed successfully!"))
    else:
        await interaction.response.send_message(embed=simple_embed("Attempted to rename an invalid Instigator Ticket"))

async def ticket_add_user(
    interaction: discord.Interaction,
    user: discord.Member
) -> None:

    if not isinstance(interaction.channel, discord.TextChannel):
        return

    bot_db = cast(Lily, interaction.client).db
    assert bot_db is not None

    try:
        owner = await bot_db.get_ticket_owner(interaction.channel.id)

        if not owner:
            await interaction.response.send_message(
                embed=simple_embed(
                    "Attempted to add a member to an invalid instigator ticket.",
                    "cross"
                )
            )
            return

        await interaction.channel.set_permissions(
            user,
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True,
            add_reactions=True,
            use_external_emojis=True,
            use_application_commands=True
        )

        await interaction.response.send_message(
            embed=simple_embed(
                f"Successfully added {user.mention} to this ticket."
            )
        )

    except discord.Forbidden:
        await interaction.response.send_message(
            embed=simple_embed(
                "Missing permissions to modify channel access.",
                "cross"
            )
        )

    except discord.HTTPException as e:
        await interaction.response.send_message(
            embed=simple_embed(
                f"Failed to add user: {e}",
                "cross"
            )
        )

    except Exception as e:
        print(f"[TICKET ADD USER ERROR] {e}")

        await interaction.response.send_message(
            embed=simple_embed(
                "An internal error occurred while adding the user.",
                "cross"
            )
        )

async def ticket_remove_user(
    interaction: discord.Interaction,
    user: discord.Member
):
    if not isinstance(interaction.channel, discord.TextChannel):
        return
    
    try:
        bot_db = cast(Lily, interaction.client).db
        assert bot_db is not None
        owner = await bot_db.get_ticket_owner(interaction.channel.id)

        if not owner:
            await interaction.response.send_message(
                embed=simple_embed(
                    "Attempted to remove a member to an invalid instigator ticket.",
                    "cross"
                )
            )
            return

        await interaction.channel.set_permissions(
            user,
            view_channel=False,
            send_messages=False,
            read_message_history=False,
            attach_files=False,
            embed_links=False,
            add_reactions=False,
            use_external_emojis=False,
            use_application_commands=False
        )

        await interaction.response.send_message(
            embed=simple_embed(
                f"Successfully removed {user.mention} from this ticket."
            )
        )

    except discord.Forbidden:
        await interaction.response.send_message(
            embed=simple_embed(
                "Missing permissions to modify channel access.",
                "cross"
            )
        )

    except discord.HTTPException as e:
        await interaction.response.send_message(
            embed=simple_embed(
                f"Failed to add user: {e}",
                "cross"
            )
        )

    except Exception as e:
        print(f"[TICKET ADD USER ERROR] {e}")

        await interaction.response.send_message(
            embed=simple_embed(
                "An internal error occurred while adding the user.",
                "cross"
            )
        )

async def ticket_close(interaction: discord.Interaction, reason: str="No reason provided"):
    if interaction.guild is None:
        await interaction.response.send_message(
            embed=simple_embed(
                "This command requires guild object inorder to execute!"
            )
        )
        return
    
    assert isinstance(interaction.user, discord.Member)

    await interaction.response.send_message(
        embed=simple_embed(
            "Ticket close scheduling has been initiated. The channel will be deleted shortly."
        ),
        ephemeral=True
    )

    message = await interaction.original_response()

    if not isinstance(interaction.channel, (discord.Thread, discord.TextChannel)):
        return await message.edit(
            embed=simple_embed(
                "Attempted to Close an invalid Instigator Ticket",
                "cross"
            )
        )

    channel = interaction.channel
    ticket_id: int = channel.id

    try:
        bot_db = cast(Lily, interaction.client).db
        assert bot_db is not None
        row = await bot_db.get_ticket_by_id(ticket_id)
        if not row:
            raise RuntimeError("Ticket data not found")

        opened_user_id, ticket_type, logs_channel_id, submission_json_raw, claimer_user_id = row
        submission_json = json.loads(submission_json_raw)

        higher_staffs_roles_id: List[int] = submission_json.get("higher_staff_role_ids", [])
        is_higher_staff = any(role.id in higher_staffs_roles_id for role in interaction.user.roles)

        if (
            claimer_user_id is not None
            and claimer_user_id != interaction.user.id
            and not is_higher_staff
        ):
            await message.edit(
                embed=simple_embed(
                    f"You cannot close this ticket.  Only <@{claimer_user_id}> can close it.",
                    "cross"
                )
            )

            return

        
        await interaction.channel.send(
            embed=build_ticket_summary(submission_json)
        )
        logs_channel = interaction.guild.get_channel(logs_channel_id)

        if not isinstance(logs_channel, discord.TextChannel):
            try:
                fetched_channel = await interaction.guild.fetch_channel(logs_channel_id)

                if isinstance(fetched_channel, discord.TextChannel):
                    logs_channel = fetched_channel
                else:
                    logs_channel = None

            except discord.NotFound:
                logs_channel = None
            except discord.Forbidden:
                logs_channel = None

        if isinstance(channel, discord.TextChannel):
            transcript_bytes = await transcript(
                interaction=interaction
            )

            if transcript_bytes is None:
                return await interaction.response.send_message("Failed to generate transcript.")


            transcript_file = discord.File(
                io.BytesIO(transcript_bytes),
                filename=f"transcript-{channel.name}.html",
            )

            proofs_reference: int = 0

            if logs_channel:
                proofs_reference = await c_ticket_log_action_channel(
                    interaction=interaction,
                    opened_user_id=opened_user_id,
                    ticket_type=ticket_type,
                    logs_channel=logs_channel,
                    transcripts_file=transcript_file,
                    transcript_file_name = f"transcript-{channel.name}.html",
                    reason=reason
                )

            """ Log the ticket """
            await bot_db.create_ticket_log(
                interaction.guild.id,
                opened_user_id,
                claimer_user_id if claimer_user_id is not None else interaction.user.id,
                reason,
                ticket_type,
                proofs_reference
            )

            """ Send DM'S to the ticket opener """
            try:
                user: discord.Member | None = interaction.guild.get_member(opened_user_id)
                if user is None:
                    user = await interaction.guild.fetch_member(opened_user_id)
                
                if user is not None:
                    embed = discord.Embed(
                        color=16777215,
                        title=f"Ticket Closed",
                        description=f"- Your support ticket was handled by {interaction.user.mention} and closed with reason {reason}\n- An copy of the transcript is attached for future reference.",
                    )

                    if interaction.guild.icon is not None:
                        embed.set_thumbnail(url=interaction.guild.icon.url)
                    
                    embed.add_field(
                        name="Server",
                        value=f"{interaction.guild.name}",
                        inline=False,
                    )

                    view = TicketLogDirectMessage(
                        ticket_type,
                        interaction.user.id,
                        reason,
                        interaction.guild.name,
                        f"transcript-{channel.name}.html"
                    )

                    await user.send(
                        view=view, 
                        file=discord.File(
                            io.BytesIO(transcript_bytes),
                            filename=f"transcript-{channel.name}.html",
                        )
                    )

            except:
                """ Silently ignore the DM """
                pass


            try:
                await channel.delete(reason=f"Ticket Closed by {interaction.user}")
            except discord.Forbidden:
                return await interaction.response.send_message("Missing permissions to delete channel.")
            except discord.HTTPException as e:
                return await interaction.response.send_message(f"Failed to delete channel: {e}")

            await bot_db.delete_ticket(ticket_id)

    except Exception as e:
        print(f"[TICKET CLOSE ERROR] {e}")

        await message.edit(
            embed=simple_embed(
                "Attempted to Close an invalid Instigator Ticket",
                "cross"
            )
        )

async def ticket_stats(interaction: discord.Interaction, member: discord.Member):

    if interaction.guild is None:
        return await interaction.response.send_message(embed=simple_embed("Please run this command inside an guild"))

    bot_db = cast(Lily, interaction.client).db
    assert bot_db is not None
    results = await bot_db.ticket_stats(interaction.guild.id, member.id)
    if not results:
        return await interaction.response.send_message(embed=simple_embed("No ticket stats found!", 'cross'))

    embed = discord.Embed(
        color=16777215,
        title=f"{member.global_name}'s Ticket Statistics",
        description=f"### Total Tickets Handled : {sum(list(results.values()))}",
    )
    for key, values in results.items():
        embed.add_field(name=key.replace("_", " ").title(), value=values)

    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_image(url=img['border'])

    await interaction.response.send_message(embed=embed)
    
async def ticket_retrieve(interaction: discord.Interaction, member_id: int):
        if interaction.guild is None:
            return

        bot_db = cast(Lily, interaction.client).db
        assert bot_db is not None
        result: List[Dict[str, Any]] = await bot_db.get_member_ticket_logs(interaction.guild.id, member_id)

        if len(result) <= 0:
            await interaction.response.send_message(
                embed=simple_embed(
                    "No ticket logs found!", 'cross'
                )
            )

            return