from discord.ext import commands

import discord, discord.app_commands as app_commands
import json
import re

from typing import Optional

from src.core.utils.embeds.sLilyEmbed import simple_embed
from src.core.features.permissions.lily_permissions import app_permission
from src.core.features.blox_fruits.routes.blox_fruits_router import BloxFruitsController
from src.core.features.blox_fruits.components.blox_fruits_components import BloxFruitsDashboard
from src.core.database.integrations.blox_fruits import BloxFruitsDatabase
from src.core.configs.path import VALUE_DB


class LilyBloxFruits(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db: Optional[BloxFruitsDatabase] = None
        self.controller: Optional[BloxFruitsController] = None

    async def on_load(self):
        self.db = await BloxFruitsDatabase.connect(str(VALUE_DB))
        self.controller = BloxFruitsController(self.db)

    async def fruits_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        if self.db is None:
            return []

        fruits = sorted(self.db.fruit_names_sorted)

        return [
            app_commands.Choice(name=fruit, value=fruit)
            for fruit in fruits
            if current.lower() in fruit.lower()
        ][:25]

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
              return

        if self.controller is not None:
            await self.controller.on_message(message, self.bot)

    bloxfruits = app_commands.Group(
            name="bloxfruits",
            description="Lily Blox Fruits Command Hierarchy!"
        )

    @bloxfruits.command(name='update_value', description='updates an value of an item in blox fruits')
    @app_commands.autocomplete(name=fruits_autocomplete)
    @app_commands.choices(
        rarity=[
            app_commands.Choice(name="Common", value="Common"),
            app_commands.Choice(name="Uncommon", value="Uncommon"),
            app_commands.Choice(name="Rare", value="Rare"),
            app_commands.Choice(name="Legendary", value="Legendary"),
            app_commands.Choice(name="Mythical", value="Mythical"),
            app_commands.Choice(name="Gamepass", value="Gamepass"),
            app_commands.Choice(name="Limited", value="Limited"),
            app_commands.Choice(name="Skins", value="Skins"),
        ],
        category=[
            app_commands.Choice(name="Common", value="Common"),
            app_commands.Choice(name="Uncommon", value="Uncommon"),
            app_commands.Choice(name="Rare", value="Rare"),
            app_commands.Choice(name="Legendary", value="Legendary"),
            app_commands.Choice(name="Mythical", value="Mythical"),
            app_commands.Choice(name="Gamepass", value="Gamepass"),
            app_commands.Choice(name="Limited", value="Limited"),
            app_commands.Choice(name="Skins", value="Skins"),
        ],
        demand_type = [
            app_commands.Choice(name="Stable", value="Stable"),
            app_commands.Choice(name="Overpaid", value="Overpaid"),
            app_commands.Choice(name="Underpaid", value="Underpaid"),
            app_commands.Choice(name="Overhyped", value="Overhyped"),
        ]
    )
    async def UpdateValue(
        self,
        interaction: discord.Interaction,
        name: str,
        physical_value: Optional[str] = None,
        permanent_value: Optional[str] = None,
        physical_demand: Optional[str] = None,
        permanent_demand: Optional[str] = None,
        demand_type: Optional[str] = None,
        permanent_demand_type: Optional[str] = None,
        category: Optional[str] = None,
        aliases: Optional[str] = None,
        icon_url: Optional[str] = None,
        rarity: Optional[str] = None
    ):
        if self.db is None:
            return

        if interaction.user.id not in (1488556914605428988, 1375441535528865832, 956179986774102106):
            return await interaction.response.send_message("Permission Denied", ephemeral=True)

        def parse_number(value: str | None) -> int | None:
            if value is None:
                return None

            value = str(value).replace(",", "").strip().lower()
            match = re.fullmatch(r"(\d+(?:\.\d+)?)([kmb]?)", value)
            if not match:
                return None

            number, suffix = match.groups()
            multiplier = {"": 1, "k": 1_000, "m": 1_000_000, "b": 1_000_000_000}
            return int(float(number) * multiplier.get(suffix, 1))

        try:
            row = await self.db.fetch_one(
                "SELECT * FROM BF_ItemValues WHERE name = ?",
                (name.title(),)
            )

            if not row:
                await interaction.response.send_message(
                    embed=simple_embed(f"No item found with name `{name}`.", 'cross'))
                return

            (
                _name,
                current_physical_value,
                current_permanent_value,
                current_physical_demand,
                current_permanent_demand,
                current_demand_type,
                current_permanent_demand_type,
                current_category,
                current_aliases,
                current_icon_url,
                current_rarity,
            ) = row

            parsed_physical_value = parse_number(physical_value)
            parsed_permanent_value = parse_number(permanent_value)

            if aliases is not None:
                alias_list = [a.strip() for a in aliases.split(",") if a.strip()]
                aliases = json.dumps(alias_list)
            else:
                aliases = current_aliases

            update_fields = {
                "physical_value": current_physical_value if parsed_physical_value is None else parsed_physical_value,
                "permanent_value": current_permanent_value if parsed_permanent_value is None else parsed_permanent_value,
                "physical_demand": physical_demand or current_physical_demand,
                "permanent_demand": permanent_demand or current_permanent_demand,
                "demand_type": demand_type or current_demand_type,
                "permanent_demand_type": permanent_demand_type or current_permanent_demand_type,
                "category": category or current_category,
                "aliases": aliases,
                "icon_url": icon_url or current_icon_url,
                "rarity": rarity or current_rarity
            }

            set_clause = ", ".join(f"{k} = ?" for k in update_fields)
            values = list(update_fields.values()) + [name.title()]

            await self.db.execute(
                f"UPDATE BF_ItemValues SET {set_clause} WHERE name = ?",
                tuple(values)
            )

            await self.db.load_cache()

            await interaction.response.send_message(embed=simple_embed(f"Updated {name} successfully."))

        except Exception as e:
            await interaction.response.send_message(embed=simple_embed("An error occurred while updating the item."))

    @bloxfruits.command(name = "dashboard", description="Spawn the customizable dashboard")
    @app_permission(command_name="staff_coverage")
    async def dashboard(self, interaction: discord.Interaction):
        await interaction.response.send_modal(BloxFruitsDashboard())

async def setup(bot):
    cog = LilyBloxFruits(bot)
    await bot.add_cog(cog)

    if hasattr(cog, "on_load"):
        await cog.on_load()