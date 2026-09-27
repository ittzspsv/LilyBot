from enum import Enum, unique


@unique
class ChannelEnum(str, Enum):
    BF_WIN_LOSS = "bf_win_loss"
    BF_FRUIT_VALUES = "bf_fruit_values"
    LOGS = "logs_channel"
    STAFF_UPDATES = "staff_updates"
    VALID_CHANNEL = "valid_channel"
    LOA_REQUEST_CHANNEL = "loa_request"