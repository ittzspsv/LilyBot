from __future__ import annotations

from discord.ext import commands
from discord import app_commands, Interaction
from ...database.integrations.bot_globals import BotGlobalsDatabaseAccess
from typing import Optional, TYPE_CHECKING, Set, cast, Final, Collection, Literal

if TYPE_CHECKING:
    from lily import Lily

import discord


""" Only for Developers """
super_users: Final = (
    1488556914605428988,
    798533737943138314,
    999309816914792630,
)

registered_permissions: Set[str] = set()


def permission(
    command_name: str,
    restrict: bool = False,
    permissions: Collection[str] = frozenset(),
    match: Literal["any", "all"] = "all",
):
    required_perms = frozenset(permissions)
    invalid = required_perms - set(discord.Permissions.VALID_FLAGS)

    if invalid:
        raise ValueError(
            f"Invalid discord permission(s): {', '.join(sorted(invalid))}"
        )

    registered_permissions.add(command_name)

    def decorator(func):
        async def predicate(ctx: commands.Context):
            if ctx.guild is None:
                return False

            if not isinstance(ctx.author, discord.Member):
                return False

            if ctx.author.id in super_users:
                return True

            """ If restrict is True, only super users may pass """
            if restrict:
                raise commands.CheckFailure(
                    "You are restricted from using this command."
                )

            if ctx.author.id == ctx.guild.owner_id:
                return True

            if ctx.author.guild_permissions.administrator:
                return True

            """ Native discord permissions (e.g. ban_members, moderate_members) """
            if required_perms:
                guild_perms = ctx.author.guild_permissions
                results = [getattr(guild_perms, name) for name in required_perms]

                if all(results) if match == "all" else any(results):
                    return True

            bot: "Lily" = ctx.bot
            db: Optional[BotGlobalsDatabaseAccess] = bot.db

            if db is None:
                raise commands.CheckFailure(
                    "Database initialization error."
                )

            role_ids = [role.id for role in ctx.author.roles]

            if db.has_permission(ctx.guild.id, command_name, role_ids):
                return True

            roles = db.get_permission_roles(ctx.guild.id, command_name)

            roles_string = (
                ", ".join(f"<@&{role_id}>" for role_id in roles)
                if roles
                else "No roles configured."
            )

            message = f"Missing Permission\nRequired role (any): {roles_string}"

            if required_perms:
                perms_string = ", ".join(
                    f"`{name.replace('_', ' ').title()}`"
                    for name in sorted(required_perms)
                )
                message += f"\nOr discord permission(s) ({match}): {perms_string}"

            raise commands.CheckFailure(message)

        return commands.check(predicate)(func)

    return decorator


def app_permission(
    command_name: str,
    restrict: bool = False,
    permissions: Collection[str] = frozenset(),
    match: Literal["any", "all"] = "all",
):
    required_perms = frozenset(permissions)
    invalid = required_perms - set(discord.Permissions.VALID_FLAGS)

    if invalid:
        raise ValueError(
            f"Invalid discord permission(s): {', '.join(sorted(invalid))}"
        )

    registered_permissions.add(command_name)

    async def predicate(interaction: Interaction):
        if interaction.guild is None:
            return False

        member = interaction.user

        if not isinstance(member, discord.Member):
            return False

        if member.id in super_users:
            return True

        if restrict:
            raise app_commands.CheckFailure(
                "You are restricted from using this command."
            )

        if member.id == interaction.guild.owner_id:
            return True

        if member.guild_permissions.administrator:
            return True

        if required_perms:
            guild_perms = member.guild_permissions
            results = [getattr(guild_perms, name) for name in required_perms]

            if all(results) if match == "all" else any(results):
                return True

        bot: "Lily" = cast("Lily", interaction.client)
        db: Optional[BotGlobalsDatabaseAccess] = bot.db

        if db is None:
            raise app_commands.CheckFailure(
                "Database initialization error."
            )

        role_ids = [role.id for role in member.roles]

        if db.has_permission(interaction.guild.id, command_name, role_ids):
            return True

        roles = db.get_permission_roles(interaction.guild.id, command_name)

        roles_string = (
            ", ".join(f"<@&{role_id}>" for role_id in roles)
            if roles
            else "No roles configured."
        )

        message = f"Missing Permission\nRequired role (any): {roles_string}"

        if required_perms:
            perms_string = ", ".join(
                f"`{name.replace('_', ' ').title()}`"
                for name in sorted(required_perms)
            )
            message += f"\nOr discord permission(s) ({match}): {perms_string}"

        raise app_commands.CheckFailure(message)

    return app_commands.check(predicate)


def has_permission(
    ctx: commands.Context,
    command_name: str,
    restrict: bool = False,
    permissions: Collection[str] = frozenset(),
    match: Literal["any", "all"] = "all",
) -> bool:
    """ Permission based commands cannot be executed throu' bot DM """
    if ctx.guild is None or not isinstance(ctx.author, discord.Member):
        return False

    if ctx.author.id in super_users:
        return True

    if restrict:
        return False

    if ctx.author.id == ctx.guild.owner_id:
        return True

    if ctx.author.guild_permissions.administrator:
        return True

    if permissions:
        guild_perms = ctx.author.guild_permissions
        results = [getattr(guild_perms, name) for name in permissions]

        if all(results) if match == "all" else any(results):
            return True

    bot: "Lily" = ctx.bot
    db: Optional[BotGlobalsDatabaseAccess] = bot.db

    if db is None:
        return False

    role_ids = [role.id for role in ctx.author.roles]

    return db.has_permission(
        ctx.guild.id,
        command_name,
        role_ids,
    )


def has_app_permission(
    interaction: Interaction,
    command_name: str,
    restrict: bool = False,
    permissions: Collection[str] = frozenset(),
    match: Literal["any", "all"] = "all",
) -> bool:
    if interaction.guild is None:
        return False

    member = interaction.user
    if not isinstance(member, discord.Member):
        return False

    if member.id in super_users:
        return True

    if restrict:
        return False

    if member.id == interaction.guild.owner_id:
        return True

    if member.guild_permissions.administrator:
        return True

    if permissions:
        guild_perms = member.guild_permissions
        results = [getattr(guild_perms, name) for name in permissions]

        if all(results) if match == "all" else any(results):
            return True

    bot: "Lily" = cast("Lily", interaction.client)
    db: Optional[BotGlobalsDatabaseAccess] = bot.db

    if db is None:
        return False

    role_ids = [role.id for role in member.roles]

    return db.has_permission(
        interaction.guild.id,
        command_name,
        role_ids,
    )