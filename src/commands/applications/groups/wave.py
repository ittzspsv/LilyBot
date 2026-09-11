from discord import app_commands


class WaveCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name="wave", description="Application Waves")
