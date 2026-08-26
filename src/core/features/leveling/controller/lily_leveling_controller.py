import discord

from typing import cast, TYPE_CHECKING
from io import BytesIO

from src.core.visuals.cards.level import create_level_card
from src.core.utils.embeds.sLilyEmbed import simple_embed
from ..utils.lily_leveling_utils import get_level_progress

if TYPE_CHECKING:
    from src.lily import Lily

async def show_level(interaction: discord.Interaction, member: discord.Member | discord.User):
    assert interaction.guild is not None
    bot_db = cast("Lily", interaction.client).db

    assert bot_db is not None


    result = await bot_db.leveling_db.get_leveling_info(
        interaction.guild.id,
        member.id
    )

    nameplate = discord.utils.find(
        lambda c: c.type is discord.CollectibleType.nameplate,
        member.collectibles
    )
    
    await interaction.response.defer()

    progress = get_level_progress(
        result["total_messages"]
    )

    bytes = await create_level_card(
        member.name,
        member.display_avatar.url,
        member.avatar_decoration.url if member.avatar_decoration else None,
        nameplate.static.url if nameplate else None,
        current_level=progress["level"],
        current_rank=result["rank"],
        current_xp=progress["current_xp"],
        max_xp = progress["max_xp"]
    )

    if bytes is None:
        await interaction.followup.send(embed=simple_embed("Failed to generate level card", 'cross'))
        return
    await interaction.followup.send(
        file=discord.File(fp=BytesIO(bytes), filename="level_card.png")
    )