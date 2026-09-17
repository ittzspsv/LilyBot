from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.lily import Lily

_bot_instance: Optional["Lily"] = None

def set_instance(bot: "Lily"):
    global _bot_instance
    _bot_instance = bot

def get_instance() -> "Lily":
    if _bot_instance is None:
        raise RuntimeError("Bot instance not set yet")
    return _bot_instance