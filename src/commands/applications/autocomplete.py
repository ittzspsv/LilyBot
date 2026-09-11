from typing import List

from discord import app_commands, Interaction


async def applications_autocomplete(
    interaction: Interaction,
    current: str,
) -> List[app_commands.Choice[int]]:
    if interaction.guild is None:
        return []

    db = getattr(interaction.client, "db", None)
    if db is None:
        return []

    applications = await db.app_management_db.get_applications_by_guild(
        guild_id=interaction.guild.id
    )

    current = current.lower()

    return [
        app_commands.Choice(
            name=application["name"],
            value=application["id"],
        )
        for application in applications
        if current in application["name"].lower()
    ][:25]


async def question_autocomplete(
    interaction: Interaction,
    current: str,
) -> List[app_commands.Choice[int]]:
    db = getattr(interaction.client, "db", None)
    if db is None or interaction.guild is None:
        return []

    questions = await db.app_management_db.get_questions_by_guild(interaction.guild.id)

    return [
        app_commands.Choice(name=q["label"][:100], value=q["id"])
        for q in questions
        if current.lower() in q["label"].lower()
    ][:25]


async def groups_autocomplete(
    interaction: Interaction,
    current: str,
) -> List[app_commands.Choice[int]]:
    db = getattr(interaction.client, "db", None)
    if db is None or interaction.guild is None:
        return []

    groups = await db.app_management_db.get_groups_by_guild(interaction.guild.id)

    return [
        app_commands.Choice(name=g["name"][:100], value=g["id"])
        for g in groups
        if current.lower() in g["name"].lower()
    ][:25]
