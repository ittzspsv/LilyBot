CREATE TABLE IF NOT EXISTS "globals" (`key` TEXT, `value` TEXT);
CREATE TABLE IF NOT EXISTS "data" (`guild_id` INTEGER PRIMARY KEY UNIQUE, prefix TEXT);
CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE IF NOT EXISTS "permissions" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER REFERENCES data(guild_id),
    role_id INTEGER,
    command TEXT,
    UNIQUE(guild_id, role_id, command)
);
CREATE TABLE IF NOT EXISTS "guild_channels" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER REFERENCES data(guild_id),
    channel_type TEXT,
    channel_id INTEGER,
    UNIQUE(guild_id, channel_type, channel_id)
);
CREATE TABLE IF NOT EXISTS "ticket_views" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    guild_id INTEGER NOT NULL REFERENCES data(guild_id),
    channel_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    config_json TEXT NOT NULL,

    UNIQUE(guild_id, channel_id, message_id)
);
CREATE TABLE IF NOT EXISTS "updates" (`next_day_update` TEXT, `next_week_update` TEXT, `next_month_update` TEXT, next_day_quota_update TEXT, next_week_quota_update TEXT, next_month_quota_update TEXT);
CREATE TABLE IF NOT EXISTS "staff_quota" (
    quota_id INTEGER PRIMARY KEY AUTOINCREMENT,

    guild_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,

    min_msg INTEGER,
    min_ms INTEGER,

    on_quota_passed TEXT,
    on_quota_failed TEXT,
    check_by TEXT,

    FOREIGN KEY (guild_id)
        REFERENCES data(guild_id),

    FOREIGN KEY (guild_id, role_id)
        REFERENCES roles(guild_id, role_id)
);
CREATE TABLE IF NOT EXISTS "members" (
    member_id INTEGER,
    guild_id INTEGER, avatar_url TEXT, `name` TEXT, timezone TEXT, prefix TEXT,
    PRIMARY KEY (member_id, guild_id),
    FOREIGN KEY (guild_id) REFERENCES data(guild_id)
);
CREATE TABLE IF NOT EXISTS "staff_roles" (
    staff_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    role_id  INTEGER NOT NULL,

    PRIMARY KEY (staff_id, guild_id, role_id),

    FOREIGN KEY (staff_id, guild_id)
        REFERENCES staffs(staff_id, guild_id),
    FOREIGN KEY (guild_id, role_id)
        REFERENCES roles(guild_id, role_id)
);
CREATE TABLE IF NOT EXISTS "leaves" (
    leave_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id   INTEGER NOT NULL,
    guild_id   INTEGER NOT NULL,
    reason     TEXT,
    days       INTEGER,
    issued_by  INTEGER, `started_on` TEXT, `ended_on` TEXT,
    FOREIGN KEY (staff_id, guild_id)
        REFERENCES staffs(staff_id, guild_id),
    FOREIGN KEY (issued_by, guild_id)
        REFERENCES staffs(staff_id, guild_id)
);
CREATE TABLE IF NOT EXISTS "rank_updates" (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    staff_id    INTEGER NOT NULL,
    updated_by  INTEGER NOT NULL,
    old_role_id INTEGER,
    new_role_id INTEGER,
    update_type TEXT CHECK(update_type IN ('promotion', 'demotion')),
    reason      TEXT,
    timestamp   TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (guild_id)
        REFERENCES data(guild_id),

    FOREIGN KEY (staff_id, guild_id)
        REFERENCES staffs(staff_id, guild_id),
        REFERENCES staffs(staff_id, guild_id),

    FOREIGN KEY (guild_id, old_role_id)
        REFERENCES roles(guild_id, role_id),

    FOREIGN KEY (guild_id, new_role_id)
        REFERENCES roles(guild_id, role_id)
);
CREATE TABLE IF NOT EXISTS "strikes" (
    strike_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    issued_by_id INTEGER NOT NULL,
    issued_to_id INTEGER NOT NULL,
    reason      TEXT,
    date        TEXT, `expiry_date` TEXT, `type` TEXT,

    FOREIGN KEY (issued_by_id, guild_id)
        REFERENCES staffs(staff_id, guild_id),

    FOREIGN KEY (issued_to_id, guild_id)
        REFERENCES staffs(staff_id, guild_id)
);
CREATE TABLE IF NOT EXISTS "messages" (
    "member_id"        INTEGER NOT NULL,
    guild_id        INTEGER NOT NULL,
    daily_messages  INTEGER DEFAULT 0,
    weekly_messages INTEGER DEFAULT 0,
    monthly_messages INTEGER DEFAULT 0,
    total_messages  INTEGER DEFAULT 0, total_xp INTEGER DEFAULT 0,

    PRIMARY KEY ("member_id", guild_id),

    FOREIGN KEY ("member_id", guild_id)
        REFERENCES members(member_id, guild_id),

    FOREIGN KEY (guild_id)
        REFERENCES data(guild_id)
);
CREATE TABLE IF NOT EXISTS "staffs" (
    staff_id        INTEGER NOT NULL,
    guild_id        INTEGER NOT NULL,
    name            TEXT    NOT NULL,
    joined_on       TEXT,
    on_loa          INTEGER DEFAULT 0,
    retired         INTEGER DEFAULT 0,
    responsibility  TEXT,
    avatar_url      TEXT, stale INTEGER DEFAULT 0,

    PRIMARY KEY (staff_id, guild_id),

    FOREIGN KEY (staff_id, guild_id)
        REFERENCES members(member_id, guild_id)
);
CREATE TABLE IF NOT EXISTS "staff_ranks" (
    role_id INTEGER,
    guild_id INTEGER,
    priority INTEGER,
    PRIMARY KEY (guild_id, role_id),
    FOREIGN KEY (guild_id) REFERENCES data(guild_id),
    FOREIGN KEY (guild_id, role_id) REFERENCES roles(guild_id, role_id)
);
CREATE TABLE IF NOT EXISTS "botlogs" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    guild_id INTEGER NOT NULL,
    member_id INTEGER NOT NULL,

    timestamp TEXT,
    log TEXT,

    FOREIGN KEY (guild_id)
        REFERENCES data(guild_id),

    FOREIGN KEY (member_id, guild_id)
        REFERENCES members(member_id, guild_id)
);
CREATE TABLE IF NOT EXISTS "tickets" (
    ticket_id INTEGER PRIMARY KEY,

    guild_id INTEGER NOT NULL
        REFERENCES data(guild_id),

    opened_user_id INTEGER NOT NULL,
    claimer_user_id INTEGER,

    submission_json TEXT,
    ticket_type TEXT,

    log_channel_id INTEGER,
    message_id INTEGER, `ticket_details_message_id` INTEGER,

    FOREIGN KEY (opened_user_id, guild_id)
        REFERENCES members(member_id, guild_id),

    FOREIGN KEY (claimer_user_id, guild_id)
        REFERENCES members(member_id, guild_id)
);
CREATE TABLE IF NOT EXISTS "role_assignments" (
    guild_id INTEGER,
    role_id INTEGER,
    target_role_id INTEGER,

    PRIMARY KEY (guild_id, role_id, target_role_id),

    FOREIGN KEY (guild_id, role_id)
        REFERENCES roles(guild_id, role_id)
        ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "roles" (
    guild_id INTEGER REFERENCES data(guild_id),
    role_id INTEGER, `role_name` TEXT,
    ban_limit INTEGER,
    ban_queue INTEGER,
    assignment_scope TEXT CHECK(assignment_scope IN ('all', 'specific', 'except', 'none')),
    role_type TEXT,

    PRIMARY KEY (guild_id, role_id)
);
CREATE TABLE IF NOT EXISTS "leaves_pending" (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    staff_id INTEGER,
    guild_id INTEGER,
    message_id INTEGER,
    reason TEXT,
    days TEXT,

    FOREIGN KEY (staff_id, guild_id)
        REFERENCES staffs(staff_id, guild_id)
);
CREATE TABLE `guild_webhooks` (`id` INTEGER PRIMARY KEY AUTOINCREMENT, `guild_id` INTEGER REFERENCES `data`(`guild_id`), `channel_type` TEXT, `webhook_url` TEXT);
CREATE TABLE roles_customize (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,

                UNIQUE (member_id, guild_id, role_id),

                FOREIGN KEY (member_id, guild_id)
                    REFERENCES members(member_id, guild_id)
            );
CREATE TABLE guild_connections (
                primary_guild_id INTEGER REFERENCES data(guild_id) ON DELETE CASCADE,
                secondary_guild_id INTEGER REFERENCES data(guild_id) ON DELETE CASCADE,

                PRIMARY KEY (primary_guild_id, secondary_guild_id),

                CHECK (primary_guild_id != secondary_guild_id)
            );
CREATE TABLE acronyms (
                member_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                acronyms TEXT NOT NULL DEFAULT '{}',

                PRIMARY KEY (member_id, guild_id),

                FOREIGN KEY (member_id, guild_id)
                    REFERENCES members(member_id, guild_id)
            );
CREATE TABLE application_questions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      guild_id INTEGER REFERENCES data(guild_id),
      label TEXT,
      description TEXT,
      placeholder TEXT,
      min_length INTEGER,
      max_length INTEGER,
      type TEXT,
      metadata TEXT
  );
CREATE TABLE application_groups (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      guild_id INTEGER REFERENCES data(guild_id),
      name TEXT,
      description TEXT
  );
CREATE TABLE application_group_questions (
        guild_id INTEGER NOT NULL REFERENCES data(guild_id),
        group_id INTEGER NOT NULL REFERENCES application_groups(id),
        question_id INTEGER NOT NULL REFERENCES application_questions(id),
        position INTEGER NOT NULL,
        PRIMARY KEY (group_id, question_id)
    );
CREATE TABLE IF NOT EXISTS "application_group_assignments" (
        guild_id INTEGER NOT NULL REFERENCES data(guild_id),
        application_id INTEGER NOT NULL REFERENCES application(id),
        group_id INTEGER NOT NULL REFERENCES application_groups(id),
        position INTEGER NOT NULL,
        PRIMARY KEY (application_id, group_id)
    );
CREATE TABLE `application_views` (`guild_id` INTEGER REFERENCES `data`(`guild_id`), `channel_id` INTEGER NOT NULL, `application_id` INTEGER REFERENCES `application`(`id`), `message_id` INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS "application_submission_answers" (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        submission_id INTEGER NOT NULL
            REFERENCES application_submissions(id) ON DELETE CASCADE, `group_id` INTEGER REFERENCES `application_groups`(`id`),
        question_id INTEGER NOT NULL
            REFERENCES application_questions(id),
        answer_value TEXT,
        UNIQUE (submission_id, question_id)
    );
CREATE TABLE IF NOT EXISTS "application_submissions" (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        application_id INTEGER NOT NULL REFERENCES application(id),
        member_id INTEGER NOT NULL,
        wave INTEGER,
        submitted_at TEXT NOT NULL DEFAULT (datetime('now')), `status` TEXT DEFAULT 'in_progress', `verification_status` TEXT DEFAULT 'pending', `submission_thread_reference` INTEGER,
        FOREIGN KEY (member_id, guild_id)
            REFERENCES members(member_id, guild_id)
        UNIQUE(guild_id, application_id, member_id, wave)
    );
CREATE TABLE IF NOT EXISTS "application_blocked_users" (
    guild_id INTEGER NOT NULL,
    member_id INTEGER NOT NULL,
    reason TEXT,
    blocked_by INTEGER,
    blocked_at TEXT NOT NULL DEFAULT (datetime('now')),

    PRIMARY KEY (guild_id, member_id),

    FOREIGN KEY (member_id, guild_id)
        REFERENCES members(member_id, guild_id)
        ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS "application" (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER REFERENCES data(guild_id),
        name TEXT,
        description TEXT, `submit_btn_label` TEXT,
        active INTEGER,
        current_wave INTEGER DEFAULT 0,
        submission_forum_id INTEGER
    );
CREATE TABLE `mod_appeal` (`case_id` INTEGER REFERENCES `modlogs`(`id`), `status` TEXT, "thread_id" INTEGER);
CREATE TABLE IF NOT EXISTS "mod_appeal_forum" (`guild_id` INTEGER UNIQUE REFERENCES `data`(`guild_id`), `config` TEXT);
CREATE TABLE IF NOT EXISTS "modlogs" (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id       INTEGER NOT NULL
                       REFERENCES data(guild_id),
    moderator_id   INTEGER NOT NULL,
    target_user_id INTEGER NOT NULL,
    mod_type       TEXT,
    reason         TEXT,
    timestamp      TEXT, deleted INTEGER DEFAULT 0, `metadata` JSON DEFAULT '{}',

    FOREIGN KEY (moderator_id, guild_id)
        REFERENCES staffs(staff_id, guild_id),

    FOREIGN KEY (target_user_id, guild_id)
        REFERENCES members(member_id, guild_id)
);
CREATE TABLE IF NOT EXISTS "proofs" (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id         INTEGER NOT NULL
                        REFERENCES modlogs(id),
    proof_reference INTEGER,
    author          INTEGER NOT NULL,
    guild_id        INTEGER NOT NULL,

    FOREIGN KEY (author, guild_id)
        REFERENCES staffs(staff_id, guild_id)
);
CREATE TABLE IF NOT EXISTS "ticket_logs" (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,

    guild_id             INTEGER NOT NULL
                             REFERENCES data(guild_id),

    opened_user_id       INTEGER NOT NULL,
    staff_handled        INTEGER,

    reason               TEXT,
    ticket_type          TEXT,
    timestamp            TEXT,
    transcripts_reference INTEGER, `logs_channel_id` INTEGER,

    FOREIGN KEY (opened_user_id, guild_id)
        REFERENCES members(member_id, guild_id),

    FOREIGN KEY (staff_handled, guild_id)
        REFERENCES staffs(staff_id, guild_id)
);
CREATE UNIQUE INDEX idx_guild_webhooks_guild_channel
    ON guild_webhooks (guild_id, channel_type);
CREATE TABLE IF NOT EXISTS "afk" (
    `member_id` INTEGER REFERENCES `members`(`member_id`),
    `guild_id` INTEGER REFERENCES `members`(`guild_id`),
    `timestamp` TEXT,
    `display_name` TEXT DEFAULT 'AFK',
    reason TEXT,
    PRIMARY KEY (`member_id`, `guild_id`)
);
CREATE TABLE IF NOT EXISTS "tasks" (
    `id`         INTEGER PRIMARY KEY AUTOINCREMENT,
    `guild_id`   INTEGER NOT NULL,
    `member_id`  INTEGER NOT NULL,
    `task_name`  TEXT NOT NULL,
    `job_type`   TEXT NOT NULL,
    `payload`    TEXT,
    `status`     TEXT NOT NULL DEFAULT 'pending',
    `run_at`     TEXT NOT NULL,
    `created_at` TEXT NOT NULL DEFAULT (datetime('now')),
    `updated_at` TEXT,
    FOREIGN KEY (`guild_id`, `member_id`) REFERENCES `members`(`guild_id`, `member_id`)
);
CREATE TABLE apscheduler_jobs (
	id VARCHAR(191) NOT NULL, 
	next_run_time FLOAT, 
	job_state BLOB NOT NULL, 
	PRIMARY KEY (id)
);
CREATE INDEX ix_apscheduler_jobs_next_run_time ON apscheduler_jobs (next_run_time);
CREATE TABLE xp_boosts (
    guild_id   INTEGER NOT NULL,
    role_id    INTEGER NOT NULL,
    multiplier REAL NOT NULL,
    PRIMARY KEY (guild_id, role_id),
    FOREIGN KEY (guild_id) REFERENCES data(guild_id)
);
