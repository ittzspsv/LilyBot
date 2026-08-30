import discord
import src.core.configs.bot_details as Configs
import io
from discord.ui import View, Button


class EmptyView(discord.ui.LayoutView):
    def __init__(self):
        self.text_display1 = discord.ui.TextDisplay(content="hi")

class GreetingComponent(View):
    def __init__(self, member: discord.Member):
        super().__init__(timeout=None)
        self.member = member

        self.add_item(
            Button(
                label="Check Rules",
                url="https://discord.com/channels/1092742448545026138/1093409671240499260",
                style=discord.ButtonStyle.link
            )
        )

class MusicPlayerView(discord.ui.View):
    def __init__(self, lavalink, guild_id):
        super().__init__(timeout=None)
        self.lavalink = lavalink
        self.guild_id = guild_id

    def disable_all(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="Add To Playlist", style=discord.ButtonStyle.secondary, custom_id="add_playlist", emoji=Configs.emoji['music_playlist'])
    async def add_playlist(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message('Added to Playlist', ephemeral=True)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.secondary, custom_id="song_stop", emoji=Configs.emoji['dnd'])
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self.lavalink.player_manager.get(self.guild_id)

        await player.stop()

        self.disable_all()

        await interaction.message.edit(view=self)

        await interaction.response.send_message("Stopped the song", ephemeral=True)

    @discord.ui.button(label="Shuffle", style=discord.ButtonStyle.secondary, custom_id="shuffle", emoji=Configs.emoji['music_shuffle'])
    async def shuffle(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message('Song Shuffled and Now Playing', ephemeral=True)

    @discord.ui.button(label="Repeat", style=discord.ButtonStyle.secondary, custom_id="repeat", emoji=Configs.emoji['music_repeat'])
    async def repeat(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self.lavalink.player_manager.get(self.guild_id)

        player.repeat = not getattr(player, "repeat", False)

        status = "enabled" if player.repeat else "disabled"

        await interaction.response.send_message(f"Repeat {status}", ephemeral=True)