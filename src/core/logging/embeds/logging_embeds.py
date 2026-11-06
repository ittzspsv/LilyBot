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