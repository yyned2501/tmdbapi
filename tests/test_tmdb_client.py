import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from typing import cast

import httpx


def load_tmdb_client_module():
    module_path = Path(__file__).resolve().parents[1] / "core" / "tmdb_client.py"

    fake_core = types.ModuleType("core")
    fake_core.__path__ = []

    fake_config_module = types.ModuleType("core.config")
    setattr(
        fake_config_module,
        "config",
        types.SimpleNamespace(
            tmdb=types.SimpleNamespace(
                base_url="https://api.themoviedb.org/3",
                api_key="test-key",
                read_access_token="",
                language="zh-CN",
                request_retries=1,
                connect_timeout=1.0,
                read_timeout=1.0,
            ),
            proxy=types.SimpleNamespace(enabled=False, http="", https=""),
        ),
    )

    fake_logger_module = types.ModuleType("core.logger")
    setattr(
        fake_logger_module,
        "logger",
        types.SimpleNamespace(
            info=lambda *args, **kwargs: None,
            warning=lambda *args, **kwargs: None,
            error=lambda *args, **kwargs: None,
        ),
    )

    sys.modules["core"] = fake_core
    sys.modules["core.config"] = fake_config_module
    sys.modules["core.logger"] = fake_logger_module

    spec = importlib.util.spec_from_file_location("tmdb_client_under_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TMDBClientRetryTest(unittest.TestCase):
    def test_5xx_retries_once_then_raises(self):
        module = load_tmdb_client_module()
        client = module.TMDBClient()

        calls = {"request": 0, "sleep": [], "reset": []}

        class FakeAsyncClient:
            async def request(self, *args, **kwargs):
                calls["request"] += 1
                return httpx.Response(
                    502,
                    text="Bad Gateway",
                    request=httpx.Request("GET", "https://api.themoviedb.org/3/tv/1"),
                )

        async def fake_get_client():
            return FakeAsyncClient()

        async def fake_release_client(client_obj):
            return None

        async def fake_reset_client(client_obj=None, reason=""):
            calls["reset"].append(reason)

        async def fake_sleep(delay):
            calls["sleep"].append(delay)

        client.get_client = fake_get_client
        client._release_client = fake_release_client
        client.reset_client = fake_reset_client
        module.asyncio.sleep = fake_sleep

        with self.assertRaises(httpx.HTTPStatusError):
            asyncio.run(client.get("tv/1"))

        self.assertEqual(calls["request"], 2)
        self.assertEqual(calls["sleep"], [2])
        self.assertEqual(calls["reset"], ["http_status_retry endpoint=tv/1 status_code=502 attempt=1"])


if __name__ == "__main__":
    unittest.main()