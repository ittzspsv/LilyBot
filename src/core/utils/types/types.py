from enum import Enum, unique


@unique
class ChannelEnum(str, Enum):
    BF_WIN_LOSS = "bf_win_loss"
    BF_FRUIT_VALUES = "bf_fruit_values"
    LOGS = "logs_channel"
    STAFF_UPDATES = "staff_updates"
    VALID_CHANNEL = "valid_channel"
    LOA_REQUEST_CHANNEL = "loa_request"

@unique
class NotifiersEnum(str, Enum):
    DAILY_MS_LEADERBOARD = "daily_ms_leaderboard"
    WEEKLY_MS_LEADERBOARD = "weekly_ms_leaderboard"
    MONTHLY_MS_LEADERBOARD = "monthly_ms_leaderboard"
    DAILY_MESSAGES_LEADERBOARD = "daily_messages_leaderboard"
    WEEKLY_MESSAGES_LEADERBOARD = "weekly_messages_leaderboard"
    MONTHLY_MESSAGES_LEADERBOARD = "monthly_messages_leaderboard"
    QUOTA_UPDATES = "quota_updates"