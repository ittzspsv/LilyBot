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

@unique
class CommandEnum(str, Enum):
    StaffData = "staff_data"
    StaffList = "staff_list"

    StrikeAdd = "strike_add"
    StrikeRemove = "strike_remove"
    StrikeEdit = "strike_edit"
    StrikeShow = "strike_show"

    StaffEdit = "staff_edit"
    StaffSelfEdit = "staff_self_edit"

    StaffAdd = "staff_add"
    StaffAddBatch = "staff_add_batch"
    StaffRemove = "staff_remove"
    StaffRemoveRaw = "staff_remove_raw"

    StaffRoles = "staff_roles"
    DevStaffUpdate = "dev_staff_update"

    LoaAdd = "loa_add"
    LoaRemove = "loa_remove"

    RankPromote = "rank_promote"
    RankPromoteBatch = "rank_promote_batch"
    RankDemote = "rank_demote"

    QuotaAdd = "quota_add"
    QuotaList = "quota_list"
    QuotaRemove = "quota_remove"
    QuotaCheck = "quota_check"
    QuotaEvaluate = "quota_evaluate"

    StaffRoleRemove = "staff_role_remove"
    StaffRoleRemoveRaw = "staff_role_remove_raw"

    Ban = "ban"
    Unban = "unban"
    Warn = "warn"
    Mute = "mute"
    Unmute = "unmute"

    Ms = "ms"
    Modlogs = "modlogs"
    ModerationInsights = "moderation_insights"

    CaseEdit = "case_edit"
    CaseEditAbsolute = "case_edit_absolute"
    CaseDelete = "case_delete"
    CaseAttach = "case_attach"
    CaseProofs = "case_proofs"

    Queue = "queue"
    QueueRemove = "queue_remove"

    TicketClose = "ticket_close"
    TicketRename = "ticket_rename"
    TicketAdd = "ticket_add"

    Purge = "purge"
    SetPrefix = "set_prefix"
    Role = "role"
    Afk = "afk"
    Nick = "nick"
    TicketStats = "ticket_stats"

    LoaDelete = "loa_delete"
    LoaRequest = "loa_request"
    LoaShow = "loa_show"

    Quarantine = "quarantine"
    Permissions = "permissions"

    SetRolecustomize = "set_rolecustomize"
    RemoveRolecustomize = "remove_rolecustomize"

    StaffCoverage = "staff_coverage"
    CreateEmbed = "create_embed"

    ModAcronymAdd = "mod_acronym_add"
    ModAcronymRemove = "mod_acronym_remove"
    ModAcronymUpdate = "mod_acronym_update"
    ModAcronyms = "mod_acronyms"

    ApplicationManagement = "application_management"
    ApplicationStaff = "application_staff"
    ApplicationBlockUnblock = "applicant_block_unblock"

    AppealManagement = "mod_appeal_management"
    AppealHandlers = "mod_appeal_handlers"

    SetAutomod = "set_automod"