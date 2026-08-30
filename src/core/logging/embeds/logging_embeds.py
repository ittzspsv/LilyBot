import discord
import src.core.configs.bot_details as Configs

from datetime import datetime

def write_log_embed(timestamp: str, user_id: int, log_text: str):
    embed = (
        discord.Embed(
            color=16777215,
            title=f"{Configs.emoji['ticket']} Logging Information",
        )
        .set_footer(text=timestamp)
        .add_field(
            name=f"{Configs.emoji['member']} User",
            value=f"<@{user_id}>",
            inline=True,
        )
        .add_field(
            name=f"{Configs.emoji['pencil']} Reason",
            value=log_text,
            inline=False,
        )
    )

    return embed

def moderation_embed(
    moderator_id: int,
    target_user_id: int,
    mod_type: str,
    reason: str,
    timestamp: datetime
) -> list[discord.Embed]:

    main_embed = discord.Embed(
        color=0xFFFFFF,
        title=f"{Configs.emoji['ticket']} Logging Information",
        timestamp=timestamp
    )

    main_embed.add_field(
        name=f"{Configs.emoji['bookmark']} Case Type",
        value=mod_type.title(),
        inline=True
    )

    main_embed.add_field(
        name=f"{Configs.emoji['member']} User",
        value=f"<@{target_user_id}>",
        inline=True
    )

    main_embed.add_field(
        name=f"{Configs.emoji['shield']} Moderator",
        value=f"<@{moderator_id}>",
        inline=True
    )

    main_embed.add_field(
        name=f"{Configs.emoji['pencil']} Reason",
        value=reason,
        inline=False
    )

    main_embed.set_image(url=Configs.img['border'])

    embeds: list[discord.Embed] = [main_embed]

    return embeds