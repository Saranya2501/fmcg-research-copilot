"""Pure sliding-window request limit helper."""

import math

def check_rate_limit(timestamps: list[float], now: float, limit: int, window: int) -> tuple[list[float], int]:
    """Return the active requests and seconds until another request is allowed."""
    active = [stamp for stamp in timestamps if now - stamp < window]
    if len(active) >= limit:
        return active, max(1, math.ceil(active[-limit] + window - now))
    return active + [now], 0
