import discord
import src.core.configs.bot_details as config

from src.core.utils.lily_utility import format_currency
from typing import List

def build_fruit_value_embed(item_data: dict) -> discord.Embed:
    embed = discord.Embed(title=item_data.get("name"),
                      colour=0xffffff)
                    
    embed.set_author(name="Item Value Calculator")

    if item_data.get('physical_value'):
        embed.add_field(
            name="Physical Value",
            value=format_currency(item_data['physical_value']),
            inline=False
        )

    if item_data.get('permanent_value'):
        embed.add_field(
            name="Permanent Value",
            value=format_currency(item_data['permanent_value']),
            inline=False
        )

    if item_data.get('physical_demand'):
        embed.add_field(
            name="Demand",
            value=item_data['physical_demand'],
            inline=False
        )

    if item_data.get('demand_type'):
        embed.add_field(
            name="Demand Type",
            value=item_data['demand_type'],
            inline=False
        )

    if item_data.get("icon_url"):
        embed.set_thumbnail(url=item_data['icon_url'])

    embed.set_footer(text="Powered By LilyValues")

    return embed

def build_win_loss_embed(
        result: dict,
        your_fruits: List[str]=[], 
        your_fruit_types: List[str]=[], 
        their_fruits: List[str]=[], 
        their_fruit_types: List[str]=[]
    ) -> discord.Embed:
    """ Preprocess values """
    your_fruit_details: str = ""
    their_fruit_details: str = ""

    def build_fruit_details(fruits: List[str], fruit_types: List[str], values, config) -> str:
        details = ""

        beli_emoji = config.emoji.get("beli", "💸")
        perm_emoji = config.emoji.get("perm", "🔒")

        for fruit, ftype, value in zip(fruits, fruit_types, values):
            fruit_emoji = config.emoji.get(fruit, "🍎")

            formatted_value = format_currency(value)

            if ftype.lower() == "permanent":
                details += f"- {perm_emoji}{fruit_emoji} {beli_emoji} {formatted_value}\n"
            else:
                details += f"- {fruit_emoji} {beli_emoji} {formatted_value}\n"

        return details
    
    your_fruit_details = build_fruit_details(
        your_fruits,
        your_fruit_types,
        result["your_individual_values"],
        config
    )

    their_fruit_details = build_fruit_details(
        their_fruits,
        their_fruit_types,
        result["their_individual_values"],
        config
    )

    """ Build Embed """
    embed = discord.Embed(description=f"## It's a {result['conclusion']} Trade",
                    colour=16777215)

    embed.add_field(name="Your Fruit Values",
                    value=your_fruit_details,
                    inline=True)
    embed.add_field(name="Their Fruit Values",
                    value=their_fruit_details,
                    inline=True)
    embed.add_field(name="Your Total Values:",
                    value=format_currency(result['your_total_values']),
                    inline=False)
    embed.add_field(name="Their Total Values:",
                    value=format_currency(result['their_total_values']),
                    inline=False)
    embed.add_field(name=f"{result['conclusion_expansion']} Percentage: {result['percentage']}%",
                    value="",
                    inline=False)
    embed.set_image(url=config.img.get("border"))

    return embed