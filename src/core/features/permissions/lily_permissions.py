from __future__ import annotations

from discord.ext import commands
from discord import app_commands, Interaction
from ...database.integrations.bot_globals import BotGlobalsDatabaseAccess
from typing import Optional, TYPE_CHECKING, List, cast, Final

if TYPE_CHECKING:
    from lily import Lily

import discord


""" Only for Developers """
super_users: Final = (
    1488556914605428988,
    798533737943138314,
    999309816914792630,
)


def permission(command_name: str, restrict: bool = False):
    def decorator(func):
        async def predicate(ctx: commands.Context):
            if ctx.guild is None:
                return False

            if not isinstance(ctx.author, discord.Member):
                return False

            if restrict:
                if ctx.author.id in super_users:
                    return True

                raise commands.CheckFailure(
                    "You are restricted from using this command."
                )

            if ctx.author.id in super_users:
                return True

            if ctx.author.id == ctx.guild.owner_id:
                return True

            if ctx.author.guild_permissions.administrator:
                return True

            bot: "Lily" = ctx.bot
            db: Optional[BotGlobalsDatabaseAccess] = bot.db

            if db is None:
                raise commands.CheckFailure(
                    "Database initialization error."
                )

            role_ids = [role.id for role in ctx.author.roles]

            has_perm = db.has_permission(
                ctx.guild.id,
                command_name,
                role_ids,
            )

            if has_perm:
                return True

            roles = db.get_permission_roles(
                ctx.guild.id,
                command_name,
            )

            roles_string = (
                ", ".join(f"<@&{role_id}>" for role_id in roles)
                if roles
                else "No roles configured."
            )

            raise commands.CheckFailure(
                f"Missing Permission\n"
                f"Required role (any): {roles_string}"
            )

        return commands.check(predicate)(func)

    return decorator


def app_permission(command_name: str, restrict: bool = False):
    async def predicate(interaction: Interaction):
        if interaction.guild is None:
            return False

        member = interaction.user

        if not isinstance(member, discord.Member):
            return False


        if restrict:
            if member.id in super_users:
                return True

            raise app_commands.CheckFailure(
                "You are restricted from using this command."
            )

        if member.id in super_users:
            return True

        if member.id == interaction.guild.owner_id:
            return True

        if member.guild_permissions.administrator:
            return True

        bot: "Lily" = cast("Lily", interaction.client)
        db: Optional[BotGlobalsDatabaseAccess] = bot.db

        if db is None:
            raise app_commands.CheckFailure(
                "Database initialization error."
            )

        role_ids = [role.id for role in member.roles]

        has_perm = db.has_permission(
            interaction.guild.id,
            command_name,
            role_ids,
        )

        if has_perm:
            return True

        roles = db.get_permission_roles(
            interaction.guild.id,
            command_name,
        )

        roles_string = (
            ", ".join(f"<@&{role_id}>" for role_id in roles)
            if roles
            else "No roles configured."
        )

        raise app_commands.CheckFailure(
            f"Missing Permission\n"
            f"Required role (any): {roles_string}"
        )

    return app_commands.check(predicate)

def has_permission(
    ctx: commands.Context,
    command_name: str,
    restrict: bool = False,
) -> bool:
    """ Permission based commands cannot be executed throu' bot DM """
    if ctx.guild is None or isinstance(ctx.author, discord.User):
        return False

    if ctx.author.id in super_users:
        return True

    """ If restrict is True, only bypass IDs may pass — deny everyone else, full stop """
    if restrict:
        return False

    """ Guild owners and administrators have access to any commands """
    if ctx.author.id == ctx.guild.owner_id:
        return True

    if ctx.author.guild_permissions.administrator:
        return True

    """ Normal permission checking based on commands """
    bot: "Lily" = ctx.bot
    db: Optional[BotGlobalsDatabaseAccess] = bot.db

    if db is None:
        return False

    role_ids = [role.id for role in ctx.author.roles]

    return db.has_permission(
        ctx.guild.id,
        command_name,
        role_ids
    )


async def has_app_permission(
    interaction: Interaction,
    command_name: str,
    restrict: bool = False,
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

    bot: "Lily" = cast("Lily", interaction.client)
    db: Optional[BotGlobalsDatabaseAccess] = bot.db
    assert db is not None

    role_ids = [role.id for role in member.roles]

    return db.has_permission(
        interaction.guild.id,
        command_name,
        role_ids,
    )