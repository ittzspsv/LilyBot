from __future__ import annotations

import discord
import re
from typing import cast, TYPE_CHECKING

from src.core.utils.embeds.sLilyEmbed import simple_embed

if TYPE_CHECKING:
    from ....lily import Lily


class ProofComponentModal(discord.ui.Modal):
    case_id = discord.ui.Label(
        text='Case ID',
        description='Please enter a case ID.',
        component=discord.ui.TextInput(
            style=discord.TextStyle.short,
            placeholder='Enter a valid case ID',
            max_length=120,
        ),
    )

    images = discord.ui.Label(
        text='Proofs',
        description='Upload any relevant proofs for this case',
        component=discord.ui.FileUpload(
            max_values=10,
            custom_id='report_images',
            required=True,
        ),
    )

    footer = discord.ui.TextDisplay(
        'Please ensure that every proof you have attached here is valid!'
    )

    def __init__(self) -> None:
        super().__init__(title="Case Proofs")

    async def on_submit(self, interaction: discord.Interaction) -> None:

        await interaction.response.defer()
        
        assert isinstance(self.images.component, discord.ui.FileUpload)
        assert isinstance(self.case_id.component, discord.ui.TextInput)

        files = self.images.component.values
        logging_controller = cast("Lily", interaction.client).logging_controller
        assert logging_controller is not None
        success = await logging_controller.send_proofs(interaction, files, int(self.case_id.component.value))

        if success:
            await interaction.followup.send(embed=simple_embed(f"Successfully appended proofs for •{self.case_id.component.value}"))
        else:
            await interaction.followup.send(embed=simple_embed(f"Failed to append proofs for •{self.case_id.component.value}. Please verify that the case ID is valid", 'cross'))

class ProofsComponentCommandModal(discord.ui.Modal):
    images = discord.ui.Label(
        text='Proofs',
        description='Upload any relevant proofs for this case',
        component=discord.ui.FileUpload(
            max_values=10,
            custom_id='report_images',
            required=True,
        ),
    )

    footer = discord.ui.TextDisplay(
        'Please ensure that every proof you have attached here is valid!'
    )

    def __init__(self, case_id: int, cmd_view: discord.ui.View, msg: discord.Message) -> None:
        super().__init__(title="Case Proofs")
        self.case_id = case_id
        self.cmd_view = cmd_view
        self.msg = msg

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        assert isinstance(self.images.component, discord.ui.FileUpload)

        files = self.images.component.values
        logging_controller = cast("Lily", interaction.client).logging_controller
        assert logging_controller is not None
        success = await logging_controller.send_proofs(interaction, files, self.case_id)

        if success:
            await interaction.followup.send(
                embed=simple_embed(
                    f"Successfully appended proofs for {self.case_id}"
                )
            )
        else:
            await interaction.followup.send(
                embed=simple_embed(
                    f"Failed to append proofs for {self.case_id}. Please verify that the case ID is valid",
                    'cross'
                )
            )