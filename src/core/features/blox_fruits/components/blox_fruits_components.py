import discord
import src.core.configs.sBotDetails as config
from ..embeds.blox_fruits_embed import build_win_loss_embed
from ..utils.trade_calculator import win_or_lose
from ..utils.trade_suggestor import trade_suggestor
from ....database.integrations.blox_fruits import BloxFruitsDatabase
from src.core.utils.lily_utility import format_currency
from typing import List
from ..utils.trade_calculator import calculate_fruit_values


class TradeSuggestorComponent(discord.ui.LayoutView):
    def __init__(self, db: BloxFruitsDatabase ,your_fruits, your_types, message, neglect_fruits, type):
        super().__init__()

        self.db = db
        self.your_fruits = your_fruits
        self.your_types = your_types
        self.message = message
        self.type = type

        self.permanent_emoji = config.emoji.get('perm')
        self.gamepass_emoji = config.fruit_emojis.get('dark_blade')
        self.fruit_skins_emoji = config.fruit_emojis.get('galaxy_kitsune')
        self.default_emoji = config.emoji.get("default") or "🍉"
        self.overpay_emoji = "🔥"
        self.fair_emoji = "🤝"

        self.include_permanent = False
        self.include_gamepass = False
        self.include_skins = False
        self.overpay = False
        self.neglect_fruits = neglect_fruits
        self.storage_capacity = 1

        self.basic_select = discord.ui.Select(
            custom_id="basic_select",
            options=[
                discord.SelectOption(label="Default", value="default", emoji=self.default_emoji),
                discord.SelectOption(label="Suggest Permanent", value="permanent", emoji=self.permanent_emoji),
                discord.SelectOption(label="Suggest Gamepass", value="gamepass", emoji=self.gamepass_emoji),
                discord.SelectOption(label="Suggest Fruit Skins", value="fruit_skins", emoji=self.fruit_skins_emoji),
            ]
        )
        self.basic_select.callback = self.basic_select_callback

        self.pricing_select = discord.ui.Select(
            custom_id="pricing",
            options=[
                discord.SelectOption(label="Fair", value="fair", emoji=self.fair_emoji),
                discord.SelectOption(label="Overpay", value="overpay", emoji=self.overpay_emoji),
            ]
        )
        self.pricing_select.callback = self.pricing_select_callback

        self.storage_select = discord.ui.Select(
            custom_id="storage_select",
            options=[discord.SelectOption(label=str(i), value=str(i), emoji=config.fruit_emojis['fruit_storage']) for i in range(1, 5)]
        )
        self.storage_select.callback = self.storage_select_callback

        self.suggest_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            label="Suggest Trade",
            custom_id="suggest_trade"
        )
        self.suggest_button.callback = self.suggest_button_callback

        container = discord.ui.Container(
            discord.ui.TextDisplay(content="## Trade Suggestor Configuration\n\n### • Customize your Suggester Settings, Then Click Suggest"),
            discord.ui.TextDisplay(content="**Basic Suggestions**"),
            discord.ui.ActionRow(self.basic_select),
            discord.ui.TextDisplay(content="**Trade Pricing Suggestions**"),
            discord.ui.ActionRow(self.pricing_select),
            discord.ui.TextDisplay(content=f"**Your Total Fruit Storage**"),
            discord.ui.ActionRow(self.storage_select),
            discord.ui.ActionRow(self.suggest_button),
            accent_colour=discord.Colour(16777215),
        )

        self.add_item(container)

    def check_user(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.message.author.id

    async def reject_user(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Only the original user can use this configuration.",
            ephemeral=True
        )

    async def basic_select_callback(self, interaction: discord.Interaction):
        if not self.check_user(interaction):
            return await self.reject_user(interaction)

        selected = self.basic_select.values[0]
        self.include_permanent = selected == "permanent"
        self.include_gamepass = selected == "gamepass"
        self.include_skins = selected == "fruit_skins"

        await interaction.response.send_message(
            f"You selected: {selected}", ephemeral=True
        )

    async def storage_select_callback(self, interaction: discord.Interaction):
        if not self.check_user(interaction):
            return await self.reject_user(interaction)

        selected = self.storage_select.values[0]
        self.storage_capacity = int(selected)

        await interaction.response.send_message(
            f"Your Max Fruit Storage Capacity is {selected}", ephemeral=True
        )

    async def pricing_select_callback(self, interaction: discord.Interaction):
        if not self.check_user(interaction):
            return await self.reject_user(interaction)

        selected = self.pricing_select.values[0]
        self.overpay = selected == "overpay"

        await interaction.response.send_message(
            f"Pricing selected: {selected}", ephemeral=True
        )

    async def suggest_button_callback(self, interaction: discord.Interaction):
        if not self.check_user(interaction):
            return await self.reject_user(interaction)

        try:
            await interaction.response.defer()

            their_fruits, their_types, success = trade_suggestor(
                self.db,
                self.your_fruits, self.your_types,
                self.include_permanent,
                self.include_gamepass,
                self.include_skins,
                self.overpay,
                self.neglect_fruits,
                self.storage_capacity
            )

            if not success:
                raise ValueError("Trade suggestion failed.")

            if self.type == 1:
                '''
                image = await StockValueJSON.j_LorW(
                    self.your_fruits, self.your_types,
                    their_fruits, their_types,
                    1, 1
                )

                if image is None:
                    raise ValueError("Image generation failed.")

                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                buffer.seek(0)

                try:
                    await interaction.delete_original_response()
                except:
                    pass

                await self.message.reply(
                    file=discord.File(fp=buffer, filename="trade_result.webp"),
                )
                '''
            else:
                data = win_or_lose(
                    self.db,
                    self.your_fruits, self.your_types,
                    their_fruits, their_types
                )

                embed = build_win_loss_embed(
                    result=data,
                    your_fruits=self.your_fruits,
                    your_fruit_types=self.your_types,
                    their_fruits=their_fruits,
                    their_fruit_types=their_types
                )
                
                try:
                    await interaction.delete_original_response()
                except:
                    pass
                await self.message.reply(embed=embed, view=InviteView())

        except Exception as e:
            try:
                await interaction.delete_original_response()
                await interaction.followup.send(
                    f"Failed to generate trade: {e}", ephemeral=True
                )
            except:
                print("Cannot send followup; interaction expired:", e)

class FruitValueComponent(discord.ui.LayoutView):
    def __init__(self, item_data: dict) -> None:

        super().__init__(timeout=10)

        value_contents: str = ""
        demand_contents: str = ""
        if item_data.get('physical_value'):
            value_contents += f"**Physical Value**\n- {format_currency(item_data['physical_value'])}\n"
        if item_data.get('permanent_value'):
            value_contents += f"**Permanent Value**\n- {format_currency(item_data['permanent_value'])}"
        if item_data.get('physical_demand'):
            demand_contents += f"**Demand**\n- {item_data['physical_demand']}\n"
        if item_data.get('demand_type'):
            demand_contents += f"**Demand Type**\n- {item_data['demand_type']}"

        
        self.container = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(content=f"# {item_data["name"]}"),
                discord.ui.TextDisplay(content=value_contents),
                discord.ui.TextDisplay(content=demand_contents),
                accessory=discord.ui.Thumbnail(
                    media=f"{item_data.get("icon_url", "")}",
                ),
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small)
        )

        self.add_item(self.container)
        self.add_item(
            discord.ui.ActionRow(
                discord.ui.Button(
                    label="Add Bot",
                    url="https://discord.com/oauth2/authorize?client_id=1240222509811499050&permissions=140794709184&integration_type=0&scope=bot",
                    style=discord.ButtonStyle.link
                )
            )  
        )

class WinLossComponent(discord.ui.LayoutView):
    def __init__(self, 
                result: dict, 
                db,
                your_fruits: List[str]=[], 
                your_fruit_types: List[str]=[], 
                their_fruits: List[str]=[], 
                their_fruit_types: List[str]=[],
        ) -> None:
        super().__init__(timeout=10)

        self.db = db

        conclusion_icon: str = ""
        fruit_suggestion_component: List = []
        if result["conclusion"] == "W":
            conclusion_icon = "https://media.discordapp.net/attachments/1510416807847133274/1511881573149052989/W.png?ex=6a2210f0&is=6a20bf70&hm=063bea7d1467b8cfc05897687dec9e4e56d8b55dbf5844151006e4c42415c942&=&format=webp&quality=lossless"
        elif result["conclusion"] == "L":
            conclusion_icon = "https://media.discordapp.net/attachments/1510416807847133274/1511881555448959096/L.png?ex=6a2210ec&is=6a20bf6c&hm=3514041a4782604f7a7f870af80507c6f2e4faa773861f2180d1f1d6afe47c62&=&format=webp&quality=lossless"

            """ Generate an suggestion for that offer """
            suggeseted_fruits, suggested_fruit_types, success = trade_suggestor(
                self.db,
                your_fruits, your_fruit_types,
                False,
                False,
                True,
                True,
                [],
                1
            )

            suggested_details = self.build_fruit_details(
                suggeseted_fruits,
                suggested_fruit_types
            )

            their_fruit_individual_values, total_value_of_their_fruit = calculate_fruit_values(
                suggeseted_fruits, suggested_fruit_types, self.db
            )

            if success:
                fruit_suggestion_component.append(
                    discord.ui.Section(
                        discord.ui.TextDisplay(content=f"## My Suggestion ({format_currency(total_value_of_their_fruit)})"),
                        discord.ui.TextDisplay(content=f"# - {suggested_details}"),
                        accessory=discord.ui.Thumbnail(
                            media="https://cdn3.emoji.gg/emojis/507611-pixelsparkle.png",
                        ),
                    ),  
                )

        else:
            conclusion_icon = "https://media.discordapp.net/attachments/1510416807847133274/1511881539279913143/F.png?ex=6a2210e8&is=6a20bf68&hm=4fc42adc6a9dc5fcd5337bd01a3d174edce969fad98ea808daac8032484cd321&=&format=webp&quality=lossless"


        your_fruit_details = self.build_fruit_details(
            your_fruits,
            your_fruit_types,
        )

        their_fruit_details = self.build_fruit_details(
            their_fruits,
            their_fruit_types,
        )

        self.container = discord.ui.Container(
            discord.ui.Section(
                discord.ui.TextDisplay(content=f"# It's a {result['conclusion']} Trade"),
                discord.ui.TextDisplay(content=f"- You {result['conclusion_expansion']} **{result['percentage']}%** value from this trade."),
                discord.ui.TextDisplay(
                    content=f"## Value Information\n### Your Offer ({format_currency(result['your_total_values'])})\n# - {your_fruit_details}\n### Their Offer ({format_currency(result['their_total_values'])})\n# - {their_fruit_details}"),
                accessory=discord.ui.Thumbnail(
                    media=conclusion_icon,
                ),
            ),
            *fruit_suggestion_component,
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small)
        )

        self.add_item(self.container)
        self.add_item(
            discord.ui.ActionRow(
                discord.ui.Button(
                    label="Add Bot",
                    url="https://discord.com/oauth2/authorize?client_id=1240222509811499050&permissions=140794709184&integration_type=0&scope=bot",
                    style=discord.ButtonStyle.link
                )
            )  
        )

    def build_fruit_details(self, fruits: List[str], fruit_types: List[str]) -> str:
        details = ""

        perm_emoji = config.emoji.get("perm", "🔒")

        for fruit, ftype in zip(fruits, fruit_types):
            fruit_name = fruit.replace(" ", "_").replace("-", "_").lower()
            fruit_emoji = config.fruit_emojis.get(fruit_name, "🍎")

            if ftype.lower() == "permanent":
                details += f"{perm_emoji}{fruit_emoji} "
            else:
                details += f"{fruit_emoji} "

        return details

class InviteView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        self.add_item(
            discord.ui.Button(
                label="Add Bot",
                url="https://discord.com/oauth2/authorize?client_id=1240222509811499050&permissions=140794709184&integration_type=0&scope=bot",
                style=discord.ButtonStyle.link
            )
        )