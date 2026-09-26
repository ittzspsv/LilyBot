import discord
import logging

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.lily import Lily

logger = logging.getLogger("lily")

from src.core.configs.bot_details import img

async def on_audit_log_entry_create(bot: "Lily", entry: discord.AuditLogEntry):
    if bot is None:
        return
    await log_role_assignments(bot, entry)


async def log_role_assignments(bot: "Lily", entry: discord.AuditLogEntry):
    if entry.action != discord.AuditLogAction.member_role_update:
        return

    assert bot is not None
    assert bot.user is not None
    assert bot.db is not None

    webhook_url = await bot.db.get_webhook(guild_id=entry.guild.id, channel_type="audit_role_updates")
    if not webhook_url:
        return

    before_roles = set(entry.before.roles or [])
    after_roles = set(entry.after.roles or [])

    added_roles = after_roles - before_roles
    removed_roles = before_roles - after_roles

    if not added_roles and not removed_roles:
        return

    target_display = f"<@{entry._target_id}>"
    actor_display = f'<@{entry.user_id}>'

    webhook = discord.Webhook.from_url(
        webhook_url,
        client=bot,
    )

    if added_roles:
        embed = discord.Embed(
            title="Role Added",
            description=f"{actor_display} added role(s) {', '.join(r.mention for r in added_roles)} to {target_display}",
            color=16777215,
        )
        embed.add_field(name="Reason", value=entry.reason or "No reason provided", inline=False)
        embed.set_image(url=img["border"])

        try:
            await webhook.send(
                username=bot.user.name,
                avatar_url=bot.user.display_avatar.url,
                embed=embed
            )
        except discord.HTTPException as e:
            if e.status == 429:
                logger.warning(f"Rate limited sending role-added webhook for guild {entry.guild.id}")
            elif e.status == 404:
                logger.warning(f"Webhook missing/deleted for guild {entry.guild.id}")
            else:
                logger.error(f"Failed to send role-added webhook for guild {entry.guild.id}: {e}")

    if removed_roles:
        embed = discord.Embed(
            title="Role Removed",
            description=f"{actor_display} removed role(s) {', '.join(r.mention for r in removed_roles)} from {target_display}",
            color=16777215,
        )
        embed.add_field(name="Reason", value=entry.reason or "No reason provided", inline=False)
        embed.set_image(url=img["border"])

        try:
            await webhook.send(
                username=bot.user.name,
                avatar_url=bot.user.display_avatar.url,
                embed=embed
            )
        except discord.HTTPException as e:
            if e.status == 429:
                logger.warning(f"Rate limited sending role-removed webhook for guild {entry.guild.id}")
            elif e.status == 404:
                logger.warning(f"Webhook missing/deleted for guild {entry.guild.id}")
            else:
                logger.error(f"Failed to send role-removed webhook for guild {entry.guild.id}: {e}")