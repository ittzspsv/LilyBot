from typing import List
from zoneinfo import available_timezones

from discord import app_commands, Interaction


async def timezone_autocomplete(interaction: Interaction, current: str) -> List[app_commands.Choice[str]]:
    matches = [
        tz for tz in sorted(available_timezones())
        if current.lower() in tz.lower()
    ]
    return [
        app_commands.Choice(name=tz, value=tz)
        for tz in matches[:25]
    ]
