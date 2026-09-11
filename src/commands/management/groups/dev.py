from discord import app_commands


class DevCommands(app_commands.Group):
    def __init__(self):
        super().__init__(name="dev", description="Developer utility commands")
