import discord
import re
from datetime import datetime
from typing import Optional
import src.core.configs.bot_details as Configs

def ParseAdvancedEmbed(data: dict):
    content = data.get("content") or None
    embeds = []
    if content:
        content = re.sub(r'@everyone|@here|<@&\d+>', '', content)
        content = re.sub(r'\s+', ' ', content).strip()

    for embed_data in data.get("embeds", []):
        try:
            color = discord.Color(embed_data.get("color", 0))
        except (ValueError, TypeError):
            color = discord.Color.default()

        embed = discord.Embed(
            title=embed_data.get("title"),
            description=embed_data.get("description"),
            url=embed_data.get("url"),
            color=color
        )

        if "timestamp" in embed_data:
            try:
                embed.timestamp = datetime.fromtimestamp(int(embed_data["timestamp"]) / 1000)
            except (ValueError, TypeError):
                pass

        if author := embed_data.get("author"):
            embed.set_author(name=author.get("name"), url=author.get("url"), icon_url=author.get("icon_url"))
        if thumbnail := embed_data.get("thumbnail"):
            embed.set_thumbnail(url=thumbnail.get("url"))
        if image := embed_data.get("image"):
            embed.set_image(url=image.get("url"))
        if footer := embed_data.get("footer"):
            embed.set_footer(text=footer.get("text"), icon_url=footer.get("icon_url"))

        for field in embed_data.get("fields", []):
            embed.add_field(
                name=field.get("name"),
                value=field.get("value"),
                inline=field.get("inline", False)
            )

        embeds.append(embed)

    return content, embeds


def simple_embed(message: str, s_emoji: str='checked', bold: bool=True, expression: Optional[str] = None) -> discord.Embed:
    emoji = Configs.emoji.get(s_emoji.lower(), "")
    text_formatting = f"{emoji} {'**' + message + '**' if bold else message}"
    embed =  discord.Embed(
        color=16777215,
        description=text_formatting,
    )

    if expression:
        embed.set_thumbnail(url=Configs.expression.get(expression) or 'neutral')
    return embed

