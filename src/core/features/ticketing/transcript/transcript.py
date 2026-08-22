import discord
from typing import Any, Dict
from src.core.configs.path import TRANSCRIPT_TEMPLATE_DIR
from jinja2 import Environment, FileSystemLoader


async def transcript(interaction: discord.Interaction):
    if not isinstance(interaction.channel, discord.TextChannel):
        return

    guild = interaction.guild

    if guild is None:
        return

    servers = [
        {
            "id": str(guild.id),
            "name": guild.name,
            "logo": guild.icon.url if guild.icon else None,
        }
    ]

    roles = {}
    for role in guild.roles:
        roles[str(role.id)] = {
            "name": role.name,
            "icon": role.icon.url if role.icon else None,
            "color": str(role.color) if role.color.value else None,
        }

    channels = {}
    for channel in guild.text_channels:
        channels[str(channel.id)] = channel.name

    messages = []
    relevant_members: Dict[str, Any] = {}

    async for message in interaction.channel.history(
        limit=None,
        oldest_first=True,
    ):

        author = message.author
        relevant_members[str(author.id)] = author

        if isinstance(author, discord.Member):
            display_name = author.display_name
            avatar_url = (
                author.display_avatar.url
                if author.display_avatar
                else None
            )

            role = author.top_role

            role_name = (
                role.name
                if role and role != guild.default_role
                else None
            )

            role_icon_url = (
                role.icon.url
                if role and role.icon
                else None
            )

        else:
            display_name = author.display_name
            avatar_url = (
                author.display_avatar.url
                if author.display_avatar
                else None
            )

            role_name = None
            role_icon_url = None
        mentions = {}

        if message.mentions:
            mentions["users"] = [
                str(user.id)
                for user in message.mentions
            ]
            for user in message.mentions:
                relevant_members[str(user.id)] = user

        if message.role_mentions:
            mentions["roles"] = [
                str(role.id)
                for role in message.role_mentions
            ]

        if message.mention_everyone:
            mentions["everyone"] = True

        attachments = []

        for attachment in message.attachments:

            attachment_data: dict[str, Any] = {
                "type": attachment.content_type.split("/")[0]
                if attachment.content_type
                else "file",

                "url": attachment.url,

                "filename": attachment.filename,
            }

            if attachment.width is not None:
                attachment_data["width"] = attachment.width

            if attachment.height is not None:
                attachment_data["height"] = attachment.height

            if attachment.size:
                attachment_data["size_bytes"] = attachment.size

            attachments.append(attachment_data)

        embeds = []

        for e in message.embeds:
            embeds.append({
                "title": e.title,
                "description": e.description,
                "url": e.url,
                "thumbnail": (
                    e.thumbnail.url
                    if e.thumbnail
                    else None
                ),
            })

        referenced_message = None

        if message.reference:

            referenced = message.reference.resolved

            if isinstance(referenced, discord.Message):

                referenced_author = referenced.author
                relevant_members[str(referenced_author.id)] = referenced_author

                referenced_message = {
                    "message_id": str(referenced.id),
                    "user_id": str(referenced_author.id),
                    "display_name": (
                        referenced_author.display_name
                    ),
                    "content_preview": (
                        referenced.content[:200]
                    ),
                }

        base_message = {
            "user_id": str(author.id),
            "display_name": display_name,
            "avatar_url": avatar_url,
            "role_icon_url": role_icon_url,
            "role_name": role_name,
            "timestamp": message.created_at.isoformat(),
            "mentions": mentions,
            "referenced_message": referenced_message,
        }

        if embeds:
            if message.content or attachments:
                messages.append({
                    **base_message,
                    "message_id": str(message.id),
                    "content": message.content,
                    "attachments": attachments,
                    "embed": None,
                })

            for idx, embed in enumerate(embeds):
                messages.append({
                    **base_message,
                    "message_id": f"{message.id}-embed-{idx}",
                    "content": "",
                    "attachments": [],
                    "embed": embed,
                })
        else:
            messages.append({
                **base_message,
                "message_id": str(message.id),
                "content": message.content,
                "attachments": attachments,
                "embed": None,
            })

    members = []
    users = {}

    for uid, person in relevant_members.items():
        avatar = (
            person.display_avatar.url
            if person.display_avatar
            else None
        )

        if isinstance(person, discord.Member):
            status = str(person.status)
            group = (
                person.top_role.name
                if person.top_role
                else "@everyone"
            )
        else:
            status = "offline"
            group = "@everyone"

        members.append({
            "id": uid,
            "displayName": person.display_name,
            "username": person.name,
            "avatar": avatar,
            "status": status,
            "group": group,
        })

        users[uid] = {
            "displayName": person.display_name,
            "username": person.name,
        }

    config = {
        "title": f"Lily-Transcript-{interaction.channel.name}",
        "servers": servers,
        "activeServerId": str(guild.id),
        "members": members,
        "roles": roles,
        "users": users,
        "channels": channels,
        "messages": messages,
    }

    env = Environment(
        loader=FileSystemLoader(TRANSCRIPT_TEMPLATE_DIR)
    )

    template = env.get_template(f"index.html")
    html = template.render(config=config)

    return html.encode("utf-8")
