from __future__ import annotations

from discord.ext import commands
from discord import app_commands, Interaction
from ...database.integrations.bot_globals import BotGlobalsDatabaseAccess
from typing import Optional, TYPE_CHECKING, List, cast

if TYPE_CHECKING:
    from lily import Lily

import discord

def permission(command_name: str, restrict: bool = False):
    def decorator(func):
        async def predicate(ctx: commands.Context): 
            """ Permission based commands cannot be executed throu' bot DM """
            if ctx.guild is None or isinstance(ctx.author, discord.User):
                return False

            if ctx.author.id in (1488556914605428988, 798533737943138314, 999309816914792630):
                return True
            
            """ Guild owners and administrators have access to any commands, unless restrict = False """
            if ctx.author.id == ctx.guild.owner_id:
                if restrict:
                    raise commands.CheckFailure("You are restricted from using this command")
                return True

            if ctx.author.guild_permissions.administrator:
                if restrict:
                    raise commands.CheckFailure("You are restricted from using this command")
                return True
                


            """ Normal permission checking based on commands """
            bot: "Lily" = ctx.bot
            db: Optional[BotGlobalsDatabaseAccess] = bot.db

            if db is None:
                raise commands.CheckFailure("Database Initialization error")
                        
            
            role_ids = [role.id for role in ctx.author.roles]

            has_perm = db.has_permission(
                ctx.guild.id,
                command_name,
                role_ids
            )

            if restrict:
                if has_perm:
                    raise commands.CheckFailure("You are restricted from using this command.")
                return True
            else:
                if not has_perm:
                    roles: List[int] = db.get_permission_roles(ctx.guild.id, command_name)
                    roles_string: str = (
                        ", ".join(f"<@&{role_id}>" for role_id in roles)
                        if roles
                        else "No roles configured."
                    )
                    raise commands.CheckFailure(
                        f"Missing Permission\n"
                        f"Required role (any): {roles_string}"
                    )
                return True

        return commands.check(predicate)(func)
    return decorator

def app_permission(command_name: str, restrict: bool = False):
    async def predicate(interaction: Interaction):
        if interaction.guild is None:
            return False

        member = interaction.user
        if not isinstance(member, discord.Member):
            return False

        if member.id in (1488556914605428988, 798533737943138314, 999309816914792630):
            return True

        if member.id == interaction.guild.owner_id:
            if restrict:
                raise app_commands.CheckFailure(
                    "You are restricted from using this command."
                )
            return True

        if member.guild_permissions.administrator:
            if restrict:
                raise app_commands.CheckFailure(
                    "You are restricted from using this command."
                )
            return True

        bot: "Lily" = cast("Lily", interaction.client)
        db: Optional[BotGlobalsDatabaseAccess] = bot.db
        assert db is not None

        role_ids = [role.id for role in member.roles]

        has_perm = db.has_permission(
            interaction.guild.id,
            command_name,
            role_ids,
        )

        if restrict:
            if has_perm:
                raise app_commands.CheckFailure(
                    "You are restricted from using this command."
                )
            return True

        if not has_perm:
            roles: List[int] = db.get_permission_roles(
                interaction.guild.id, command_name
            )
            roles_string: str = (
                ", ".join(f"<@&{role_id}>" for role_id in roles)
                if roles
                else "No roles configured."
            )
            raise app_commands.CheckFailure(
                f"Missing Permission\n"
                f"Required role (any): {roles_string}"
            )

        return True

    return app_commands.check(predicate)

def has_permission(
    ctx: commands.Context,
    command_name: str,
    restrict: bool = False,
) -> bool:
    """ Permission based commands cannot be executed throu' bot DM """
    if ctx.guild is None or isinstance(ctx.author, discord.User):
        return False

    if ctx.author.id in (1488556914605428988, 798533737943138314, 999309816914792630):
        return True

    """ Guild owners and administrators have access to any commands, unless restrict = False """
    if ctx.author.id == ctx.guild.owner_id:
        if restrict:
            return False
        return True

    if ctx.author.guild_permissions.administrator:
        if restrict:
            return False
        return True

    """ Normal permission checking based on commands """
    bot: "Lily" = ctx.bot
    db: Optional[BotGlobalsDatabaseAccess] = bot.db

    if db is None:
        return False

    role_ids = [role.id for role in ctx.author.roles]

    has_perm = db.has_permission(
        ctx.guild.id,
        command_name,
        role_ids
    )

    if restrict:
        return not has_perm

    return has_perm

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

    if member.id in (1488556914605428988, 798533737943138314, 999309816914792630):
        return True

    if member.id == interaction.guild.owner_id:
        if restrict:
            return False
        return True

    if member.guild_permissions.administrator:
        if restrict:
            return False
        return True

    bot: "Lily" = cast("Lily", interaction.client)
    db: Optional[BotGlobalsDatabaseAccess] = bot.db
    assert db is not None

    role_ids = [role.id for role in member.roles]

    has_perm = db.has_permission(
        interaction.guild.id,
        command_name,
        role_ids,
    )

    if restrict:
        return not has_perm

    return has_perm