from ....database.integrations.blox_fruits import BloxFruitsDatabase
from ...blox_fruits.utils.trade_matcher import match_fruit_set
from ..utils.trade_extractor import extract_trade_details
from ..utils.trade_calculator import win_or_lose
from ....visuals.cards.fruit_values import value_img
from ....visuals.cards.win_loss import win_loss_img
from typing import Optional, Any
from ..components.blox_fruits_components import TradeSuggestorComponent, FruitValueComponent, WinLossComponent
from io import BytesIO

import re
import asyncio
import discord

class BloxFruitsController:
    def __init__(self, db: BloxFruitsDatabase):
        super().__init__()

        self.db = db
        self.img_mode: int = 0

    def strip_mention(self, content: str, bot_user_id: int) -> str:
        return re.sub(rf"<@!?{bot_user_id}>", "", content).strip().lower()

    async def _reply(self, message: discord.Message, bot: Any) -> bool:
        ref = message.reference
        if ref is None:
            return False

        resolved = ref.resolved
        if isinstance(resolved, discord.Message):
            return resolved.author.id == bot.user.id

        return False

    async def on_message(self, message: discord.Message, bot: Optional[Any] = None):
        if message.author.bot:
            return
        if not bot or message.guild is None:
            return

        is_mention = bot.user in message.mentions
        is_reply_to_bot = await self._reply(message, bot)

        if not (is_mention or is_reply_to_bot):
            return

        if message.channel.id in bot.db.get_channels(message.guild.id, "bf_fruit_values"):
            await self.fruit_value(message=message, bot=bot)

        elif message.channel.id in bot.db.get_channels(message.guild.id, "bf_win_loss"):
            await self.win_loss(message=message, bot=bot)

        elif message.channel.id in bot.db.get_channels(message.guild.id, "bf_trading_channels"):
            await self.bf_automoderation(message, bot.db)


    async def fruit_value(self, message: discord.Message, bot: Any):
        item_name = re.sub(r"^(perm|permanent|fruit value of|value of|value)\s+", "", self.strip_mention(message.content, bot.user.id)).strip()

        alias_map = self.db.alias_map
        item_name = match_fruit_set(item_name, set(self.db.fruit_names_sorted), alias_map)

        if item_name:
            item_data = self.db.fetch_fruit_details(item_name)
            if isinstance(item_data, dict):
                overload_data = {
                    "fruit_name": item_data.get("name") or "Unknown",
                    "physical_value": item_data.get("physical_value") or "0",
                    "permanent_value": item_data.get("permanent_value") or "0",
                    "value": item_data.get("physical_value") or "0",
                    "demand": item_data.get("physical_demand") or "0",
                    "demand_type": item_data.get("demand_type") or "..",
                    "icon_url": (
                        item_data.get("icon_url")
                        or getattr(message.author.display_avatar, "url", None)
                    ),
                }

                if self.img_mode == 1:
                    img = await asyncio.to_thread(value_img, overload_data)
                    buffer = BytesIO()
                    img.save(buffer, format="PNG")
                    buffer.seek(0)

                    file = discord.File(buffer, filename=f"value.png")
                    await message.reply(file=file)

                else:
                    #embed = build_fruit_value_embed(item_data)
                    view = FruitValueComponent(item_data)

                    #if len(embed.fields) > 0:
                    await message.reply(view=view)

    async def win_loss(self, message: discord.Message, bot: Any):
        your_fruits, your_fruit_types, their_fruits, their_fruit_types = extract_trade_details(self.strip_mention(message.content, bot.user.id), self.db)
        if not any([
            your_fruits,
            your_fruit_types,
            their_fruits,
            their_fruit_types
        ]):
            return

        """ Check for fruit_suggestor fallback """
        if bool(your_fruits) != bool(their_fruits):
            fruits = your_fruits if your_fruits else their_fruits
            fruit_types = your_fruit_types if your_fruits else their_fruit_types            
            await self.trade_suggestor(message, fruits, fruit_types)

        else: 
            """ Normal w or l evaluation here"""
            calculated_result = win_or_lose(
                self.db,
                your_fruits[:4],
                your_fruit_types[:4],
                their_fruits[:4],
                their_fruit_types[:4]
            )

            if self.img_mode == 1:
                """ Generate win-loss image """
                img = await asyncio.to_thread(
                    win_loss_img, 
                    your_fruits, 
                    calculated_result["your_individual_values"], 
                    their_fruits,
                    calculated_result["their_individual_values"],
                    your_fruit_types,
                    their_fruit_types,
                    calculated_result["conclusion"],
                    calculated_result["conclusion_expansion"],
                    calculated_result["percentage"]
                )
                buffer = BytesIO()
                img.save(buffer, format="PNG")
                buffer.seek(0)

                file = discord.File(buffer, filename=f"value.png")
                await message.reply(file=file)
            else:
                """ Send embed """
                """
                embed = build_win_loss_embed(
                    calculated_result,
                    your_fruits[:4],
                    your_fruit_types[:4],
                    their_fruits[:4],
                    their_fruit_types[:4]
                )
                """

                view = WinLossComponent(
                    calculated_result,
                    self.db,
                    your_fruits[:4],
                    your_fruit_types[:4],
                    their_fruits[:4],
                    their_fruit_types[:4]
                )

                #await message.reply(embed=embed, view=InviteView())
                await message.reply(view=view)

    async def bf_automoderation(self, message: discord.Message, bot_db):
        your_fruits, your_fruit_types, their_fruits, their_fruit_types = extract_trade_details(message.content, self.db)
        if not any([your_fruits, your_fruit_types]) or not any([their_fruits, their_fruit_types]):
            return
        
        
        calculated_result = win_or_lose(
                self.db,
                your_fruits[:4],
                your_fruit_types[:4],
                their_fruits[:4],
                their_fruit_types[:4]
            )
        
        """ Check if the value difference on their side is less than 60% """
        if calculated_result["percentage"] > 60 and calculated_result["conclusion"].lower() == 'l':
            """ It might be phishing.  Why not we actually DM them to find that out """


            """ If they actually respond and if that's a phishing link, we just quarantine them with appropriate reason"""
            channel_id = bot_db.get_channel(message.guild.id, "logs_channel")
            if channel_id is None:
                return
            try:
                assert isinstance(message.guild, discord.Guild)
                logs_channel = await message.guild.fetch_channel(channel_id)

                if not isinstance(logs_channel, discord.TextChannel):
                    return

                await logs_channel.send(embed=discord.Embed(
                    title="Trade Scam Detected",
                    description=(
                        f"This trade [Message]({message.jump_url}) sent by {message.author.mention} seems too good to be true.\n\n"
                        f"**Trade Value Difference:** {calculated_result['percentage']}%\n\n"
                        f"**Value Information**\n"
                        f"**Your Offer:** {calculated_result['your_total_values']}\n"
                        f"**Their Offer:** {calculated_result['their_total_values']}\n\n"
                        f"Necessary actions have been taken against the user."
                    )
                ))

            except Exception:
                return


    async def trade_suggestor(self, message: discord.Message ,fruits, fruit_types):
        view = TradeSuggestorComponent(
            self.db,
            fruits,
            fruit_types,
            message,
            [],
            self.img_mode
        )

        await message.reply(view=view)