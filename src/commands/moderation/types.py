from enum import Enum


class ModType(str, Enum):
    All = "all"
    Ban = "ban"
    Warn = "warn"
    Mute = "mute"
    Quarantine = "quarantine"
    Unmute = "unmute"
    QuarantineRelease = "quarantine_release"
    Unban = "unban"
