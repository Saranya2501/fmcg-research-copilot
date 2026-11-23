"""Shared, binary-safe Redis connection for future cache and vector workloads."""

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def get_redis_client():
    """Return a verified pooled client, or None when Redis is not configured.

    Binary responses preserve FLOAT32 embedding bytes for vector search. Callers
    share the connection pool; they should not close the client themselves.
    """
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        return None

    from redis import Redis

    client = Redis.from_url(
        url,
        decode_responses=False,
        socket_connect_timeout=3,
        socket_timeout=5,
        health_check_interval=30,
        max_connections=20,
    )
    try:
        client.ping()
        # Read-only check that Redis Search (including VECTOR indexes) exists.
        client.execute_command("FT._LIST")
    except Exception:
        client.close()
        raise
    return client
