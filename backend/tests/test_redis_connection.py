import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storage.redis_connection import get_redis_client


class RedisConnectionTests(unittest.TestCase):
    def setUp(self):
        get_redis_client.cache_clear()
        self.redis = MagicMock()
        self.client = self.redis.Redis.from_url.return_value
        self.modules = patch.dict(sys.modules, {"redis": self.redis})
        self.modules.start()

    def tearDown(self):
        get_redis_client.cache_clear()
        self.modules.stop()

    def test_unconfigured_local_run_needs_no_redis(self):
        with patch.dict(os.environ, {"REDIS_URL": ""}):
            self.assertIsNone(get_redis_client())
        self.redis.Redis.from_url.assert_not_called()

    def test_shared_binary_safe_client_checks_search(self):
        with patch.dict(os.environ, {"REDIS_URL": "redis://redis:6379/0"}):
            self.assertIs(get_redis_client(), self.client)
            self.assertIs(get_redis_client(), self.client)
        self.redis.Redis.from_url.assert_called_once()
        self.assertFalse(self.redis.Redis.from_url.call_args.kwargs["decode_responses"])
        self.client.ping.assert_called_once()
        self.client.execute_command.assert_called_once_with("FT._LIST")

    def test_failed_search_check_closes_client_and_allows_retry(self):
        self.client.execute_command.side_effect = [RuntimeError("Search missing"), []]
        with patch.dict(os.environ, {"REDIS_URL": "redis://redis:6379/0"}):
            with self.assertRaisesRegex(RuntimeError, "Search missing"):
                get_redis_client()
            self.client.close.assert_called_once()
            self.assertIs(get_redis_client(), self.client)
