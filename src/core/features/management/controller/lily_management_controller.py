from __future__ import annotations

from ....database.integrations.bot_globals import BotGlobalsDatabaseAccess
from src.core.configs.bot_details import emoji, img
from src.core.utils.embeds.sLilyEmbed import simple_embed
from ..types.staff_management_types import QuotaCheckBy
from typing import Optional, cast, Final, TYPE_CHECKING
from ..embeds.staff_management_embed import *
from src.core.features.permissions.lily_permissions import has_app_permission

import matplotlib.pyplot as plt
import re

from ..components.staff_management_components import (
    StaffsView,
    LOARequestModal,
    StrikesListView,
    StaffDataView
)

import discord
import asyncio
import logging

logger = logging.getLogger("lily")

from io import BytesIO

if TYPE_CHECKING:
    from src.lily import Lily


quota_conclusion_mapping: Final = {
    "1d": "Daily",
    "7d": "Weekly",
    "30d": "Monthly"
}


async def fetch_staff_detail(ctx: discord.Interaction | commands.Context, staff: discord.Member | discord.User) -> None:
    if ctx.guild is None:
        embed = simple_embed("This command can only be used inside a guild", 'cross')
        if isinstance(ctx, discord.Interaction):
            await ctx.response.send_message(embed=embed, ephemeral=True)
        else:
            await ctx.reply(embed=embed, ephemeral=True)
        return

    try:
        client = ctx.client if isinstance(ctx, discord.Interaction) else ctx.bot
        bot_db = cast("Lily", client).db
        assert bot_db is not None

        data_dict = await bot_db.fetch_staff_detail(staff.id, ctx.guild.id)

        if not data_dict:
            raise ValueError("Staff data not found in database.")

        view = StaffDataView(staff, data_dict)

        if isinstance(ctx, discord.Interaction):
            await ctx.response.send_message(view=view)
        else:
            await ctx.reply(view=view)

    except Exception:
        logger.exception(f"[FetchStaffDetail] Failed to fetch staff data for staff_id={staff.id}")

        embed = simple_embed("No staff data found", 'cross')
        if isinstance(ctx, discord.Interaction):
            await ctx.response.send_message(embed=embed, ephemeral=True)
        else:
            await ctx.reply(embed=embed, ephemeral=True)

async def fetch_all_staffs(ctx: discord.Interaction | commands.Context) -> None:
    if ctx.guild is None:
        embed = discord.Embed(
            title=f"{emoji['cross']} Error",
            description="Cannot execute this command without an guild object",
            colour=0xf50000
        )
        if isinstance(ctx, discord.Interaction):
            await ctx.response.send_message(embed=embed)
        else:
            await ctx.reply(embed=embed)
        return

    client = ctx.client if isinstance(ctx, discord.Interaction) else ctx.bot
    bot_db = cast("Lily", client).db
    assert bot_db is not None

    try:
        data = await bot_db.fetch_staff_summary(ctx.guild.id)
        ranks = await bot_db.get_staff_ranks(ctx.guild.id)

        view = StaffsView(ctx, ranks, data)

        if isinstance(ctx, discord.Interaction):
            await ctx.response.send_message(view=view, ephemeral=True)
        else:
            await ctx.reply(view=view, ephemeral=True)

    except Exception:
        logger.exception(f"[FetchAllStaffs] Failed to fetch staff list for guild_id={ctx.guild.id}")

        embed = simple_embed("No staff data returned", 'cross')
        if isinstance(ctx, discord.Interaction):
            await ctx.response.send_message(embed=embed, ephemeral=True)
        else:
            await ctx.reply(embed=embed, ephemeral=True)

async def update_all_staffs(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        embed = discord.Embed(
            title=f"{emoji['cross']} Error",
            description="Cannot execute this command without a guild object",
            colour=0xf50000
        )
        await interaction.response.send_message(embed=embed)
        return

    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None

    guild_id = interaction.guild.id

    rows = await bot_db.fetch_all(
        "SELECT staff_id FROM staffs WHERE retired = 0 AND on_loa = 0 AND guild_id = ?",
        (guild_id,)
    )
    staff_ids = [row["staff_id"] for row in rows]

    db_roles = await bot_db.fetch_all(
        "SELECT role_id, role_type FROM roles WHERE guild_id = ?",
        (guild_id,)
    )
    staff_role_ids          = {r["role_id"] for r in db_roles if r["role_type"] == "staff"}
    responsibility_role_ids = {r["role_id"] for r in db_roles if r["role_type"] == "responsibility"}

    for staff_id in staff_ids:
        try:
            staff_member = interaction.guild.get_member(staff_id)
            if not staff_member:
                try:
                    staff_member = await interaction.guild.fetch_member(staff_id)
                except discord.NotFound:
                    logger.warning(f"[UpdateAllStaffs] Member not found in guild, skipping: staff_id={staff_id} guild_id={guild_id}")
                    continue

            top_staff_role = None
            for role in reversed(staff_member.roles):
                if role.id in staff_role_ids:
                    top_staff_role = role
                    break

            discord_responsibilities = {
                role.id for role in staff_member.roles
                if role.id in responsibility_role_ids
            }

            await bot_db.execute(
                "DELETE FROM staff_roles WHERE staff_id = ? AND guild_id = ?",
                (staff_id, guild_id)
            )

            if top_staff_role is None and not discord_responsibilities:
                await bot_db.execute(
                    "UPDATE staffs SET retired = 1 WHERE staff_id = ? AND guild_id = ?",
                    (staff_id, guild_id)
                )
                continue

            await bot_db.execute(
                """
                UPDATE staffs
                SET retired = 0, avatar_url = ?
                WHERE staff_id = ? AND guild_id = ?
                """,
                (staff_member.display_avatar.url, staff_id, guild_id)
            )

            if top_staff_role is not None:
                await bot_db.execute(
                    """
                    INSERT OR IGNORE INTO staff_roles (staff_id, guild_id, role_id)
                    VALUES (?, ?, ?)
                    """,
                    (staff_id, guild_id, top_staff_role.id)
                )

            if discord_responsibilities:
                await bot_db.executemany(
                    """
                    INSERT OR IGNORE INTO staff_roles (staff_id, guild_id, role_id)
                    VALUES (?, ?, ?)
                    """,
                    [(staff_id, guild_id, rid) for rid in discord_responsibilities]
                )

            logger.info(f"[UpdateAllStaffs] Updated {staff_member.name} (staff_id={staff_id}, guild_id={guild_id})")

        except Exception:
            logger.exception(f"[UpdateAllStaffs] Exception while updating staff_id={staff_id} guild_id={guild_id}")
            continue

        await asyncio.sleep(1)

    await interaction.response.send_message(embed=simple_embed("Updated every staff role in the database!"))

async def add_staff(interaction: discord.Interaction, staff: discord.Member, rank: discord.Role | None = None) -> None:
    if interaction.guild is None:
        embed = discord.Embed(
            title=f"{emoji['cross']} Error",
            description="Cannot execute this command without an guild object",
            colour=0xf50000
        )

        await interaction.response.send_message(embed=embed)
        return

    assert isinstance(interaction.user, discord.Member)

    if rank is not None and interaction.user.top_role <= rank:
        await interaction.response.send_message(
            embed=simple_embed(
                "You cannot assign a rank higher than or equal to your own.",
                "cross",
            )
        )
        return

    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None
    try:
        response = await bot_db.add_staff(staff.id, interaction.guild.id, staff.display_name, staff.display_avatar.url, role_id=rank.id if rank else None)

        if not response.get("success"):
            await interaction.response.send_message(embed=simple_embed(response.get("message") or "Unknown Object Passed and Failed", "cross"))
            return

        roles_to_add = set(response.get("roles_to_add", ()))

        add_roles = {
            interaction.guild.get_role(role_id)
            for role_id in roles_to_add
        }
        add_roles = {r for r in add_roles if r}

        if add_roles:
            await staff.add_roles(*add_roles, reason=f"Staff added by {interaction.user.id}")

        await interaction.response.send_message(embed=simple_embed(response.get("message") or "Unknown object passed as an output, But it's a success!"))
    except Exception:
        logger.exception(f"[AddStaff] Failed to add staff_id={staff.id} in guild_id={interaction.guild.id}")
        await interaction.response.send_message(embed=simple_embed("Failed to add staff.", "cross"))

async def remove_staff(interaction: discord.Interaction, staff: discord.Member | discord.User, reason: str) -> None:
    if interaction.guild is None:
        embed = discord.Embed(
            title=f"{emoji['cross']} Error",
            description="Cannot execute this command without an guild object",
            colour=0xf50000
        )

        await interaction.response.send_message(embed=embed)
        return
    bot_db = cast("Lily", interaction.client).db
    assert bot_db is not None
    try:
        response = await bot_db.remove_staff(staff.id, interaction.guild.id)

        if not response.get("success"):
            await interaction.response.send_message(embed=simple_embed(response.get("message") or "Unknown object has been passed and it failed!", "cross"))
            return

        roles_to_remove = set(response.get("roles_to_remove", ()))
        channel_id = bot_db.get_channel(interaction.guild.id, "staff_updates")

        staff_updates_channel: discord.TextChannel | None = None

        if channel_id is not None:
            channel = interaction.guild.get_channel(channel_id)

            if channel is None:
                try:
                    channel = await interaction.guild.fetch_channel(channel_id)
                except Exception:
                    logger.exception(f"[RemoveStaff] Failed to fetch staff_updates channel_id={channel_id} in guild_id={interaction.guild.id}")
                    channel = None

            if isinstance(channel, discord.TextChannel):
                staff_updates_channel = channel

        if staff:
            remove_roles = {
                interaction.guild.get_role(role_id)
                for role_id in roles_to_remove
            }
            remove_roles = {r for r in remove_roles if r}

            if remove_roles and isinstance(staff, discord.Member):
                try:
                    await staff.remove_roles(
                        *remove_roles,
                        reason=f"Staff removed by {interaction.user.id} | {reason}"
                    )
                except Exception:
                    logger.exception(f"[RemoveStaff] Failed to remove roles from staff_id={staff.id} in guild_id={interaction.guild.id}")

            if staff_updates_channel:
                embed = build_staff_update_embed(
                    staff=staff,
                    handled_staff=interaction.user,
                    reason=reason,
                    img=img
                )
                try:
                    await staff_updates_channel.send(
                        embed=embed
                    )
                except Exception:
                    logger.exception(f"[RemoveStaff] Failed to send staff update embed to channel_id={staff_updates_channel.id} in guild_id={interaction.guild.id}")

        await interaction.response.send_message(embed=simple_embed(response.get("message") or "Unknown object has been passed, but it's an success!"))
        """ Send DM'S If Available """

        if staff is not None:
            assert isinstance(interaction.user, discord.Member)
            try:
                await staff.send(
                    embed=staff_remove_embed(
                        interaction.user,
                        reason,
                        interaction.guild.name
                    )
                )
            except Exception:
                logger.exception(f"[RemoveStaff] Failed to DM staff_id={staff.id} about their removal (likely DMs closed)")
    except Exception:
        logger.exception(f"[RemoveStaff] Unhandled exception while removing staff_id={staff.id} in guild_id={interaction.guild.id}")

async def edit_staff(interaction: discord.Interaction, staff_id: int, name: str, joined_on: Optional[str] = None, timezone: Optional[str] = None, responsibility: Optional[str] = None):
    if interaction.guild is None:
        embed = discord.Embed(
            title=f"{emoji['cross']} Error",
            description="Cannot execute this command without an guild object",
            colour=0xf50000
        )

        await interaction.response.send_message(embed=embed)
        return
    try:
        payload = {
            "staff_id": staff_id,
            "guild_id": interaction.guild.id,
            "name": name,
            "joined_on": joined_on,
            "timezone": timezone,
            "responsibility": responsibility
        }

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
        result = await bot_db.edit_staff(**payload)

        if result.get("success"):
            await interaction.response.send_message(
                embed=simple_embed(
                    result["message"]
                )
            )
        else:
            await interaction.response.send_message(
                embed=simple_embed(
                    result["message"], 'cross'
                )
            )
    except Exception:
        logger.exception(f"[EditStaff] Failed to edit staff_id={staff_id} in guild_id={interaction.guild.id}")
        await interaction.response.send_message(embed=simple_embed("Failed to edit staff.", "cross"))

async def strike_staff(
    interaction: discord.Interaction,
    staff: discord.Member,
    reason: str,
    type: str,
    notify_staff: bool,
    notify_staff_updates: bool,
    expire_after: str
):
    assert isinstance(interaction.guild, discord.Guild)
    assert isinstance(interaction.user, discord.Member)

    try:
        await interaction.response.defer()
    except discord.HTTPException:
        logger.exception(
            "strike_staff: failed to defer interaction (staff_id=%s)",
            staff.id,
        )
        return

    normalized_expiry = expire_after.strip().lower()
    if not re.fullmatch(r"none|\d{1,4}[dhwm]", normalized_expiry):
        await _safe_followup(
            interaction,
            f"Invalid expiry format: `{expire_after}`. Use something like `1d`, `22d`, or `none`.",
            is_error=True,
        )
        return

    try:
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
    except Exception:
        logger.exception(
            "strike_staff: failed to resolve bot_db (staff_id=%s)",
            staff.id,
        )
        await _safe_followup(interaction, "An internal error occurred.", is_error=True)
        return

    payload = {
        "staff_id": staff.id,
        "guild_id": interaction.guild.id,
        "issued_by": interaction.user.id,
        "reason": reason,
        "type": type,
        "expiry_date": normalized_expiry,
    }

    try:
        response = await bot_db.strike_staff(**payload)
    except Exception:
        logger.exception(
            "strike_staff: strike_staff DB call failed (staff_id=%s, guild_id=%s)",
            staff.id, interaction.guild.id,
        )
        await _safe_followup(interaction, "An unknown error occurred while recording the infraction.", is_error=True)
        return

    if not response.get("success"):
        await _safe_followup(interaction, response.get("message") or "An unknown object has been returned and failed", is_error=True)
        return

    message = response.get("message")
    strike_reason = response.get("reason")

    if notify_staff:
        try:
            await staff.send(embed=infraction_embed(interaction.user, reason, interaction.guild.name, type.replace("_", " ").lower()))
        except discord.HTTPException:
            logger.exception(
                "strike_staff: failed to DM staff member infraction notice (staff_id=%s)",
                staff.id,
            )

    await _safe_followup(interaction, message or "An unknown object has been returned, but It's an success!")

    if not notify_staff_updates:
        return

    """ Build an embed so that we can post it on the staff updates channel"""

    try:
        channel_id = bot_db.get_channel(interaction.guild.id, "staff_updates")
    except Exception:
        logger.exception(
            "strike_staff: get_channel lookup failed (guild_id=%s)",
            interaction.guild.id,
        )
        channel_id = None

    try:
        border_media = img['border']
    except KeyError:
        logger.exception("strike_staff: 'border' key missing from Configs.img")
        border_media = None

    embed = discord.Embed(
        color=16777215,
        title="Infraction Information",
        description=f"### {staff.mention} has been issued with {type.replace("_", " ").title()}"
    )
    embed.set_thumbnail(url=staff.display_avatar.url)
    if border_media is not None:
        embed.set_image(url=border_media)

    embed.add_field(
        name="Reason",
        value=f"- {strike_reason}",
        inline=False,
    )

    staff_updates_channel: Optional[discord.TextChannel] = None

    if channel_id is not None:
        channel = interaction.guild.get_channel(channel_id)

        if channel is None:
            try:
                channel = await interaction.guild.fetch_channel(channel_id)
            except discord.HTTPException:
                logger.exception(
                    "strike_staff: failed to fetch staff updates channel (channel_id=%s, guild_id=%s)",
                    channel_id, interaction.guild.id,
                )
                channel = None

        if isinstance(channel, discord.TextChannel):
            staff_updates_channel = channel

    if staff_updates_channel:
        try:
            await staff_updates_channel.send(
                content=staff.mention,
                embed=embed
            )
        except discord.HTTPException:
            logger.exception(
                "strike_staff: failed to post infraction embed to staff updates channel (channel_id=%s, staff_id=%s)",
                staff_updates_channel.id, staff.id,
            )

async def _safe_followup(interaction: discord.Interaction, message: str, is_error: bool = False):
    try:
        await interaction.followup.send(
            embed=simple_embed(message, 'cross') if is_error else simple_embed(message),
        )
    except discord.HTTPException:
        logger.exception(
            "_safe_followup: failed to send followup (user_id=%s)",
            interaction.user.id,
        )


async def remove_strike_staff(interaction: discord.Interaction, strike_id: int):
    if interaction.guild is None:
        embed = discord.Embed(
            title=f"{emoji['cross']} Error",
            description="Cannot execute this command without an guild object",
            colour=0xf50000
        )

        await interaction.response.send_message(embed=embed)
        return
    try:
        payload = {
            "strike_id": strike_id,
            "guild_id": interaction.guild.id
        }

        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
        result = await bot_db.remove_strike(**payload)

        status: bool = bool(result.get("success"))
        message: str = str(result.get("message") or "An unknown error occurred")

        if status:
            await interaction.response.send_message(embed=simple_embed(message))

            """ Notify the staff that his strike has been removed """
            staff_id: int = cast(int, result.get("issued_to"))
            issued_by: int = cast(int, result.get("issued_by"))
            reason: str = cast(str, result.get("reason"))

            staff_member = interaction.guild.get_member(staff_id)
            if staff_member is None:
                try:
                    staff_member = await interaction.guild.fetch_member(staff_id)
                except Exception:
                    logger.exception(f"[RemoveStrikeStaff] Failed to fetch staff_id={staff_id} in guild_id={interaction.guild.id} to notify strike removal")
                    return
            assert isinstance(interaction.user, discord.Member)
            try:
                await staff_member.send(embed=staff_strike_remove_embed(interaction.user, issued_by, reason, interaction.guild.name))
            except Exception:
                logger.exception(f"[RemoveStrikeStaff] Failed to DM staff_id={staff_id} about strike removal (likely DMs closed)")

        else:
            await interaction.response.send_message(embed=simple_embed(message, "cross"))
    except Exception:
        logger.exception(f"[RemoveStrikeStaff] Unhandled exception while removing strike_id={strike_id} in guild_id={interaction.guild.id}")

async def list_strikes(interaction: discord.Interaction, staff: discord.Member):
    if interaction.guild is None:
        await interaction.response.send_message(embed=simple_embed("Cannot execute this command without a guild object", 'cross'), ephemeral=True)
        return

    try:
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
        strikes_list_data = await bot_db.fetch_staff_strikes(
            staff_id=staff.id,
            guild_id=interaction.guild.id
        )

        view = StrikesListView(
            (interaction.user.display_name, interaction.user.display_avatar.url),
            strikes_list_data=strikes_list_data,
            db=bot_db,
            guild_id=interaction.guild.id,
            staff_id=staff.id,
            elevated=has_app_permission(interaction, "strike_add")
        )

        await interaction.response.send_message(
            view=view,
            ephemeral=True
        )
        
    except Exception:
        logger.exception(f"[ListStrikes] Failed to fetch strikes for staff_id={staff.id} in guild_id={interaction.guild.id}")
        await interaction.response.send_message(embed=simple_embed("Failed to fetch strikes.", "cross"))

async def edit_strike(interaction: discord.Interaction, strike_id: int, new_reason: str):
    if interaction.guild is None:
        embed = discord.Embed(
            title=f"{emoji['cross']} Error",
            description="Cannot execute this command without a guild object",
            colour=0xf50000
        )
        await interaction.response.send_message(embed=embed)
        return

    try:
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
        response = await bot_db.edit_strike(**{
            "guild_id": interaction.guild.id,
            "strike_id": strike_id,
            "staff_id": interaction.user.id,
            "new_reason": new_reason
        })

        if not response.get("success"):
            await interaction.response.send_message(embed=simple_embed(str(response.get("message")), 'cross'))
            return

        await interaction.response.send_message(embed=simple_embed(str(response.get("message"))))
    except Exception:
        logger.exception(f"[EditStrike] Failed to edit strike_id={strike_id} in guild_id={interaction.guild.id}")
        await interaction.response.send_message(embed=simple_embed("Failed to edit strike.", "cross"))

async def add_loa(interaction: discord.Interaction, staff: discord.Member, reason: str):
    if interaction.guild is None:
        embed = discord.Embed(
            title=f"{emoji['cross']} Error",
            description="Cannot execute this command without a guild object",
            colour=0xf50000
        )
        await interaction.response.send_message(embed=embed)
        return
    try:
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
        response = await bot_db.add_loa(**{
            "staff_id": staff.id,
            "reason": reason,
            "loa_issued_by": interaction.user.id,
            "guild_id": interaction.guild.id
        })

        if not response.get("success"):
            await interaction.response.send_message(embed=simple_embed(str(response.get("message")), 'cross'))
            return

        roles_to_remove = set(response.get("roles_to_remove", ()))
        roles_to_add = set(response.get("roles_to_add", ()))

        current_roles = set(staff.roles)

        remove_roles = {
            interaction.guild.get_role(rid)
            for rid in roles_to_remove
        }
        remove_roles = {r for r in remove_roles if r}

        add_roles = {
            interaction.guild.get_role(rid)
            for rid in roles_to_add
        }
        add_roles = {r for r in add_roles if r}

        new_roles = (current_roles - remove_roles) | add_roles

        await staff.edit(
            roles=list(new_roles),
            reason="LOA assigned"
        )

        await interaction.response.send_message(embed=simple_embed(str(response.get("message"))))
    except Exception:
        logger.exception(f"[AddLOA] Failed to add LOA for staff_id={staff.id} in guild_id={interaction.guild.id}")
        await interaction.response.send_message(embed=simple_embed("Failed to add LOA.", "cross"))

async def remove_loa(interaction: discord.Interaction, staff: discord.Member):
    if interaction.guild is None:
        embed = discord.Embed(
            title=f"{emoji['cross']} Error",
            description="Cannot execute this command without a guild object",
            colour=0xf50000
        )
        await interaction.response.send_message(embed=embed)
        return
    try:
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
        response = await bot_db.remove_loa(**{"staff_id": staff.id, "guild_id": interaction.guild.id})

        if not response.get("success"):
            await interaction.response.send_message(embed=simple_embed(str(response.get("message"))))
            return

        roles_to_remove = set(response.get("roles_to_remove", ()))
        roles_to_add = set(response.get("roles_to_add", ()))

        current_roles = set(staff.roles)

        remove_roles = {
            interaction.guild.get_role(rid)
            for rid in roles_to_remove
        }
        remove_roles = {r for r in remove_roles if r}

        add_roles = {
            interaction.guild.get_role(rid)
            for rid in roles_to_add
        }
        add_roles = {r for r in add_roles if r}

        new_roles = (current_roles - remove_roles) | add_roles

        await staff.edit(
            roles=list(new_roles),
            reason="LOA removed"
        )

        await interaction.response.send_message(embed=simple_embed(str(response.get("message"))))
    except Exception:
        logger.exception(f"[RemoveLOA] Failed to remove LOA for staff_id={staff.id} in guild_id={interaction.guild.id}")
        await interaction.response.send_message(embed=simple_embed("Failed to remove LOA.", "cross"))

async def list_loa(interaction: discord.Interaction, staff: discord.Member):
    if interaction.guild is None:
        return await interaction.response.send_message(embed=simple_embed("Run this command only inside a guild", 'cross'))

    try:
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
        results = await bot_db.loa_list(staff.id, interaction.guild.id)

        if len(results) <= 0:
            return await interaction.response.send_message(embed=simple_embed("No LOA found for this user", 'cross'))

        embed = discord.Embed(
            color=16777215,
            description=f"### Listing LOA for {staff.mention}\n",
        )

        embed.set_thumbnail(url=staff.display_avatar.url)
        embed.set_image(url=img['border'])

        for result in results:
            embed.add_field(
                name=f"📌 LOA #{result['leave_id']}",
                value=f"- **Reason**: {result['reason']}\n- **Assigned by**: <@{result['issued_by']}>",
                inline=False
            )

        await interaction.response.send_message(embed=embed)
    except Exception:
        logger.exception(f"[ListLOA] Failed to list LOA for staff_id={staff.id} in guild_id={interaction.guild.id}")
        await interaction.response.send_message(embed=simple_embed("Failed to list LOA.", "cross"))

async def request_loa(interaction: discord.Interaction):
    try:
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
        await interaction.response.send_modal(LOARequestModal(bot_db))
    except Exception:
        logger.exception(f"[RequestLOA] Failed to open LOA request modal for user_id={interaction.user.id}")

async def loa_delete(interaction: discord.Interaction, leave_id: int):
    try:
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
        await bot_db.delete_loa(leave_id=leave_id)
        await interaction.response.send_message(embed=simple_embed("Successfully deleted LOA"))
    except Exception:
        logger.exception(f"[LOADelete] Failed to delete leave_id={leave_id}")
        await interaction.response.send_message(embed=simple_embed("Failed to delete LOA.", "cross"))

async def get_all_staff_roles(interaction: discord.Interaction):
    if interaction.guild is None:
        embed = discord.Embed(
            title=f"{emoji['cross']} Error",
            description="Cannot execute this command without a guild object",
            colour=0xf50000
        )
        await interaction.response.send_message(embed=embed)
        return

    try:
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
        rows = await bot_db.fetch_all(
            """
            SELECT role_id, priority
            FROM staff_ranks
            WHERE guild_id = ?
            ORDER BY priority ASC
            """,
            (interaction.guild.id,)
        )

        if not rows:
            await interaction.response.send_message(embed=simple_embed("No staff roles found in this guild.", 'cross'))
            return

        role_names = []
        role_mentions = []
        priorities = []

        for role_id, priority in rows:
            role = interaction.guild.get_role(role_id)

            priorities.append(str(priority))

            if role:
                role_names.append(role.name)
                role_mentions.append(role.mention)
            else:
                role_names.append(f"Unknown Role ({role_id})")
                role_mentions.append(f"<@&{role_id}>")

        embed = discord.Embed(
            title="Permission Assigned Roles",
            colour=0xffffff
        )

        embed.add_field(
            name="Role Names",
            value="\n".join(role_names),
            inline=True
        )

        embed.add_field(
            name="Role Reference",
            value="\n".join(role_mentions),
            inline=True
        )

        embed.add_field(
            name="Priority",
            value="\n".join(priorities),
            inline=True
        )

        await interaction.response.send_message(embed=embed)

    except Exception:
        logger.exception(f"[GetAllStaffRoles] Failed to fetch staff roles for guild_id={interaction.guild.id}")
        await interaction.response.send_message(embed=simple_embed("Error fetching staff roles", 'cross'))

async def update_staff(interaction: discord.Interaction, staff: discord.Member, reason: str, update_type: str, rank: discord.Role | None = None) -> None:
    if interaction.guild is None:
        embed = discord.Embed(
            title=f"{emoji['cross']} Error",
            description="Cannot execute this command without a guild object",
            colour=0xf50000
        )
        await interaction.response.send_message(embed=embed)
        return

    if interaction.user.id == staff.id:
        await interaction.response.send_message(embed=simple_embed(
            "You cannot update your",
            "cross"
        ))
        return

    try:
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
        assert isinstance(interaction.user, discord.Member)

        elevated = (
            interaction.user.guild_permissions.administrator
            or interaction.user == interaction.guild.owner
        )

        result = await bot_db.update_staff(
            guild_id=interaction.guild.id,
            staff_id=staff.id,
            update_type=update_type,
            reason=reason,
            updated_by=interaction.user.id,
            elevated=elevated,
            rank_id=rank.id if rank else None
        )

        if not result.get("success"):
            await interaction.response.send_message(embed=simple_embed(
                str(result.get("message")),
                "cross"
            ))
            return

        channel_id = bot_db.get_channel(
            interaction.guild.id,
            "staff_updates"
        )

        staff_updates_channel: discord.TextChannel | None = None

        if channel_id is not None:
            channel = interaction.guild.get_channel(channel_id)

            if channel is None:
                try:
                    channel = await interaction.guild.fetch_channel(channel_id)
                except Exception:
                    logger.exception(f"[UpdateStaff] Failed to fetch staff_updates channel_id={channel_id} in guild_id={interaction.guild.id}")
                    channel = None

            if isinstance(channel, discord.TextChannel):
                staff_updates_channel = channel

        old_role_id = result.get("old_role_id")
        new_role_id = result.get("new_role_id")

        old_role = interaction.guild.get_role(old_role_id) if old_role_id else None
        new_role = interaction.guild.get_role(new_role_id) if new_role_id else None

        try:
            current_roles = set(staff.roles)

            if old_role:
                current_roles.discard(old_role)

            if new_role:
                current_roles.add(new_role)

            await staff.edit(
                roles=list(current_roles),
                reason=f"Staff {update_type.title()} | {reason}"
            )

        except Exception as e:
            logger.exception(f"[UpdateStaff] Database updated but Discord role update failed for staff_id={staff.id} in guild_id={interaction.guild.id}")
            await interaction.response.send_message(embed=simple_embed(
                f"Database updated, but Discord role update failed: {e}",
                "cross"
            ))
            return

        embed = build_staff_update_result_embed(
            staff=staff,
            interaction=interaction,
            old_role_id=old_role_id,
            new_role_id=new_role_id,
            reason=reason,
            update_type=update_type
        )

        if staff_updates_channel:
            try:
                await staff_updates_channel.send(
                    content=staff.mention,
                    embed=embed
                )
            except Exception:
                logger.exception(f"[UpdateStaff] Failed to send update embed to channel_id={staff_updates_channel.id} in guild_id={interaction.guild.id}")

        act = "promoted" if update_type == "promotion" else "demoted"

        await interaction.response.send_message(
            embed=simple_embed(f"{staff.mention} has been {act}.")
        )
    except Exception:
        logger.exception(f"[UpdateStaff] Unhandled exception while updating staff_id={staff.id} in guild_id={interaction.guild.id}")
        await interaction.response.send_message(embed=simple_embed("Failed to update staff.", "cross"))


async def add_staff_quota(interaction: discord.Interaction, quota_role: discord.Role, minimum_ms: int, minimum_msg: int, check_by: QuotaCheckBy):
    if interaction.guild is None:
        embed = discord.Embed(
            title=f"{emoji['cross']} Error",
            description="Cannot execute this command without a guild object",
            colour=0xf50000
        )
        await interaction.response.send_message(embed=embed)
        return

    try:
        payload = {
            "guild_id": interaction.guild.id,
            "role_id": quota_role.id,
            "min_msg": minimum_msg,
            "min_ms": minimum_ms,
            "check_by": check_by
        }
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
        result = await bot_db.add_staff_quota(**payload)

        if not result.get("success"):
            await interaction.response.send_message(embed=simple_embed(str(result.get("message")), 'cross'))
            return

        await interaction.response.send_message(embed=simple_embed(str(result.get("message"))))
    except Exception:
        logger.exception(f"[AddStaffQuota] Failed to add quota for role_id={quota_role.id} in guild_id={interaction.guild.id}")
        await interaction.response.send_message(embed=simple_embed("Failed to add staff quota.", "cross"))

async def remove_staff_quota(interaction: discord.Interaction, quota_id: str):
    if interaction.guild is None:
        embed = discord.Embed(
            title=f"{emoji['cross']} Error",
            description="Cannot execute this command without a guild object",
            colour=0xf50000
        )
        await interaction.response.send_message(embed=embed)
        return
    try:
        payload = {
            "guild_id": interaction.guild.id,
            "quota_id": int(quota_id)
        }
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
        result = await bot_db.remove_staff_quota(**payload)

        if not result.get("success"):
            await interaction.response.send_message(embed=simple_embed(str(result.get("message")), 'cross'))
            return

        await interaction.response.send_message(embed=simple_embed(str(result.get("message"))))
    except Exception:
        logger.exception(f"[RemoveStaffQuota] Failed to remove quota_id={quota_id} in guild_id={interaction.guild.id}")
        await interaction.response.send_message(embed=simple_embed("Failed to remove staff quota.", "cross"))

async def fetch_staff_quota(interaction: discord.Interaction):
    if interaction.guild is None:
        embed = discord.Embed(
            title=f"{emoji['cross']} Error",
            description="Cannot execute this command without a guild object",
            colour=0xf50000
        )
        await interaction.response.send_message(embed=embed)
        return

    try:
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
        quotas = await bot_db.fetch_staff_quota(interaction.guild.id)

        if not quotas:
            return await interaction.response.send_message(embed=simple_embed("No staff quotas configured.", 'cross'))

        embed = discord.Embed(
            title="Staff Quota",
            description="- Showing all defined Staff Quota for this Server",
            color=16777215
        )

        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        embed.set_image(url=img['border'])

        for quota in quotas:
            role = interaction.guild.get_role(quota["role_id"])
            role_mention = role.mention if role else f"`{quota['role_id']}`"

            embed.add_field(
                name=f"Quota #{quota['quota_id']}",
                value=(
                    f"- Role : {role_mention}\n"
                    f"- Minimum Messages : {quota['min_msg']}\n"
                    f"- Minimum Moderation Stats : {quota['min_ms']}\n"
                    f"- Quota Check By : {quota['check_by'] or 'None'}"
                ),
                inline=False
            )

        await interaction.response.send_message(embed=embed)
    except Exception:
        logger.exception(f"[FetchStaffQuota] Failed to fetch quotas for guild_id={interaction.guild.id}")
        await interaction.response.send_message(embed=simple_embed("Failed to fetch staff quotas.", "cross"))

async def check_staff_quota(interaction: discord.Interaction, staff: discord.Member | discord.User):
    if interaction.guild is None:
        embed = discord.Embed(
            title=f"{emoji['cross']} Error",
            description="Cannot execute this command without a guild object",
            colour=0xf50000
        )
        await interaction.response.send_message(embed=embed)
        return
    try:
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
        response = await bot_db.get_staff_current_quota(**{
            "guild_id": interaction.guild.id,
            "staff_id": staff.id
        })

        if not response.get("success"):
            return await interaction.response.send_message(embed=simple_embed(f"{response.get('message')}", 'cross'))

        msgs = response["messages"]
        quota = response["quota"]
        result = response["result"]
        mod_stats = response.get("mod_stats_weekly", {})

        min_msg = quota.get("min_msg", 0) or 0
        min_ms = quota.get("min_ms", 0) or 0
        weekly = msgs.get("weekly", 0) or 0
        weekly_ms = mod_stats.get("weekly_ms", 0)
        weekly_ms = weekly_ms or 0

        remaining_msg = max(min_msg - weekly, 0)
        remaining_ms = max(min_ms - weekly_ms, 0)

        overall_status = (
            f"## {emoji['checked']} Passed"
            if result.get("message_quota_passed") and result.get("ms_quota_passed")
            else f"## {emoji['cross']} Failed"
        )

        msg_status = (
            f"{emoji['checked']} Passed ({weekly}/{min_msg})"
            if result.get("message_quota_passed")
            else f"{emoji['cross']} Failed ({weekly}/{min_msg}, need {remaining_msg} more)"
        )

        ms_status = (
            f"{emoji['checked']} Passed ({weekly_ms}/{min_ms})"
            if result.get("ms_quota_passed")
            else f"{emoji['cross']} Failed ({weekly_ms}/{min_ms}, need {remaining_ms} more)"
        )

        embed = discord.Embed(
            title=f"Displaying Quota Status for {staff}",
            description=overall_status,
            color=16777215
        )

        embed.set_thumbnail(url=staff.display_avatar.url)

        embed.add_field(
            name="Results",
            value=(
                f"- **Messages:** {msg_status}\n"
                f"- **Moderation:** {ms_status}"
            ),
            inline=False
        )

        embed.set_footer(text=f"Staff ID: {response['staff_id']}")

        await interaction.response.send_message(embed=embed)
    except Exception:
        logger.exception(f"[CheckStaffQuota] Failed to check quota for staff_id={staff.id} in guild_id={interaction.guild.id}")
        await interaction.response.send_message(embed=simple_embed("Failed to check staff quota.", "cross"))

async def remove_role(interaction: discord.Interaction, role: int):
    if interaction.guild is None:
        embed = discord.Embed(
            title=f"{emoji['cross']} Error",
            description="Cannot execute this command without a guild object",
            colour=0xf50000
        )
        await interaction.response.send_message(embed=embed)
        return
    try:
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
        response = await bot_db.remove_role(interaction.guild.id, role)

        if response.get("success"):
            await interaction.response.send_message(embed=simple_embed(f"{response.get('message')}"), allowed_mentions=discord.AllowedMentions.none())
        else:
            await interaction.response.send_message(embed=simple_embed(f"{response.get('message')}", 'cross'))
    except Exception:
        logger.exception(f"[RemoveRole] Failed to remove role_id={role} in guild_id={interaction.guild.id}")
        await interaction.response.send_message(embed=simple_embed("Failed to remove role.", "cross"))

async def evaluate_staff_quota(interaction: discord.Interaction, role: discord.Role):
    if interaction.guild is None:
        embed = discord.Embed(
            title=f"{emoji['cross']} Error",
            description="Cannot execute this command without a guild object",
            colour=0xf50000
        )
        await interaction.response.send_message(embed=embed)
        return
    try:
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
        quota_id = await bot_db.get_quota_id_from_role(interaction.guild.id, role.id)
        if quota_id is None:
            return await interaction.response.send_message(
                embed=simple_embed("No quota has been defined for this role", 'cross')
            )

        response = await bot_db.get_quota_status(
            interaction.guild.id,
            quota_id,
        )

        if not response.get("success"):
            return await interaction.response.send_message(
                embed=simple_embed(
                    response.get("message", "Error occurred"),
                    'cross'
                )
            )

        quota = response["quota"]
        summary = response["summary"]

        passed_staff = response["passed_staff"]
        failed_staff = response["failed_staff"]

        passed_staff_str = "\n".join(
            f"<@{s['staff_id']}>"
            for s in passed_staff
        ) or "None"

        failed_staff_str = "\n".join(
            (
                f"<@{s['staff_id']}>"
            )
            for s in failed_staff
        ) or "None"

        embed = discord.Embed(
            color=0xFFFFFF,
            description=f"### Quota Evaluation for <@&{quota['role_id']}>"
        )

        embed.add_field(
            name="Quota Summary",
            value=(
                f"Total Staff: **{summary['total_staff']}**\n"
                f"Passed: **{summary['passed']}**\n"
                f"Failed: **{summary['failed']}**"
            ),
            inline=False,
        )

        embed.add_field(
            name="Passed Staff",
            value=passed_staff_str,
            inline=False,
        )

        embed.add_field(
            name="Failed Staff",
            value=failed_staff_str,
            inline=False,
        )

        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)

        embed.set_image(url=img['border'])

        await interaction.response.send_message(embed=embed)
    except Exception:
        logger.exception(f"[EvaluateStaffQuota] Failed to evaluate quota for role_id={role.id} in guild_id={interaction.guild.id}")
        await interaction.response.send_message(embed=simple_embed("Failed to evaluate staff quota.", "cross"))

async def get_staffs_timezone_coverage(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message(embed=simple_embed("This command can only be executed inside an guild", 'cross'))
        return

    await interaction.response.defer()

    try:
        bot_db = cast("Lily", interaction.client).db
        assert bot_db is not None
        result = await bot_db.get_staffs_timezone_coverage(interaction.guild.id)
        data = sorted(result.items(), key=lambda x: x[1])

        zones = [x[0] for x in data]
        counts = [x[1] for x in data]

        fig, ax = plt.subplots(figsize=(10, max(5, 0.5 * len(zones))))

        fig.patch.set_facecolor("#111214")
        ax.set_facecolor("#111214")

        bars = ax.barh(
            zones,
            counts,
            color="#5a5a5a",
            edgecolor="#d0d0d0",
            linewidth=1.5,
            height=0.6
        )

        max_count = max(counts) if counts else 0
        ax.set_xlim(0, max(1, max_count * 1.15))

        ax.tick_params(
            axis="x",
            bottom=False,
            labelbottom=False
        )

        ax.tick_params(
            axis="y",
            colors="#d0d0d0",
            labelsize=13,
            length=0
        )

        for spine in ax.spines.values():
            spine.set_visible(False)

        ax.grid(False)

        for bar in bars:
            width = bar.get_width()
            ax.text(
                width + max_count * 0.02,
                bar.get_y() + bar.get_height() / 2,
                str(int(width)),
                va="center",
                ha="left",
                color="#d0d0d0",
                fontsize=12,
                fontweight="bold"
            )

        ax.margins(y=0.02)

        plt.tight_layout()

        buffer = BytesIO()
        plt.savefig(
            buffer,
            format="png",
            dpi=150,
            facecolor="#111214",
            bbox_inches="tight"
        )
        plt.close(fig)
        buffer.seek(0)

        file = discord.File(
            buffer,
            filename="staff_timezone_coverage.png"
        )

        await interaction.followup.send(file=file)
    except Exception:
        logger.exception(f"[GetStaffsTimezoneCoverage] Failed to generate timezone coverage chart for guild_id={interaction.guild.id}")
        await interaction.followup.send(embed=simple_embed("Failed to generate timezone coverage chart.", "cross"))

async def automatic_quota_evaluator(check_by: str, bot):
    try:
        _bot = cast("Lily", bot)
        bot_db = _bot.db
        assert bot_db is not None
        data = await bot_db.get_webhooks_of_type("quota_updates")
    except Exception:
        logger.exception(f"[AutomaticQuotaEvaluator] Failed to fetch webhooks of type 'quota_updates' for check_by={check_by}")
        return

    for guild_id, webhook_url in data.items():
        if webhook_url is None:
            continue

        try:
            webhook = discord.Webhook.from_url(webhook_url, client=bot)
        except ValueError:  # Failed to fetch the webhook
            logger.warning(f"[AutomaticQuotaEvaluator] Invalid webhook URL for guild_id={guild_id}, skipping")
            continue

        """ Else start evaluating """
        try:
            quota_ids = await bot_db.get_quota_ids_from_checkby(guild_id, check_by)
        except Exception:
            logger.exception(f"[AutomaticQuotaEvaluator] Failed to fetch quota ids for guild_id={guild_id} check_by={check_by}")
            continue

        if len(quota_ids) <= 0:
            continue

        for quota_id in quota_ids:
            try:
                """ If we have an valid quota id then let's evaluate and post the result """
                response = await bot_db.get_quota_status(
                    guild_id,
                    quota_id,
                )

                """ If any error occures let's silently skip the iterration """

                if not response.get("success"):
                    logger.warning(f"[AutomaticQuotaEvaluator] Quota evaluation failed: {response.get('message')} guild_id={guild_id} quota_id={quota_id}")
                    continue

                quota = response["quota"]
                summary = response["summary"]

                passed_staff = response["passed_staff"]
                failed_staff = response["failed_staff"]

                passed_staff_str = "\n".join(
                    f"<@{s['staff_id']}>"
                    for s in passed_staff
                ) or "None"

                failed_staff_str = "\n".join(
                    (
                        f"<@{s['staff_id']}>"
                    )
                    for s in failed_staff
                ) or "None"

                embed = discord.Embed(
                    color=0xFFFFFF,
                    description=f"### Quota Evaluation for <@&{quota['role_id']}>"
                )

                embed.add_field(
                    name="Quota Summary",
                    value=(
                        f"Total Staff: **{summary['total_staff']}**\n"
                        f"Passed: **{summary['passed']}**\n"
                        f"Failed: **{summary['failed']}**"
                    ),
                    inline=False,
                )

                embed.add_field(
                    name="Passed Staff",
                    value=passed_staff_str,
                    inline=False,
                )

                embed.add_field(
                    name="Failed Staff",
                    value=failed_staff_str,
                    inline=False,
                )

                embed.set_image(url=img['border'])

                try:
                    _payload = {
                        "username": f"{_bot.user.name if _bot.user else "Lily"} {quota_conclusion_mapping.get(check_by, 'Unknown')} Quota Updates",
                        "embed": embed
                    }

                    if _bot.user:
                        _payload["avatar_url"] = _bot.user.display_avatar.url,
                    await webhook.send(
                        **_payload
                    )
                except Exception:
                    logger.exception(f"[AutomaticQuotaEvaluator] Failed to send webhook for guild_id={guild_id} quota_id={quota_id}")
                    continue
            except Exception:
                logger.exception(f"[AutomaticQuotaEvaluator] Unhandled exception while evaluating quota_id={quota_id} for guild_id={guild_id}")
                continue