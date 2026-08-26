SQLITE_MAX_INT = 9223372036854775807 

B, C = 5, 4 


def total_messages_for_level(level: int) -> int:
    if level <= 0:
        return 0
    L = level
    return B * L * (L - 1) // 2 + C * L


def level_from_messages(total_messages: int) -> int:
    if total_messages <= 0:
        return 0

    lo, hi = 0, 1
    while total_messages_for_level(hi) <= total_messages:
        hi *= 2
        if hi > 2_000_000:
            break

    while lo < hi:
        mid = (lo + hi + 1) // 2
        if total_messages_for_level(mid) <= total_messages:
            lo = mid
        else:
            hi = mid - 1
    return lo


def get_level_progress(total_messages: int) -> dict:
    total_messages = max(0, min(total_messages, SQLITE_MAX_INT))

    level = level_from_messages(total_messages)
    floor_for_level = total_messages_for_level(level)
    ceiling_for_next_level = total_messages_for_level(level + 1)

    return {
        "level": level,
        "current_xp": total_messages - floor_for_level,
        "max_xp": ceiling_for_next_level - floor_for_level,
        "total_messages": total_messages,
    }