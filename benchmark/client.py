from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any

from .settings import setting

logger = logging.getLogger(__name__)


class BenchmarkHttpPublisher:
    def __init__(self, *, base_url: str | None = None, timeout_s: float = 2.0) -> None:
        self.base_url = str(base_url or setting("benchmark_api_url", os.getenv("BENCHMARK_API_URL", "http://127.0.0.1:8090"))).rstrip("/")
        self.timeout_s = timeout_s
        self._last_warning_at = 0.0
        self.enabled = bool(setting("benchmark_publish_events", os.getenv("BENCHMARK_PUBLISH_EVENTS", "true").lower() == "true"))

    async def publish_transcript(self, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        try:
            await asyncio.to_thread(self._post_json, "/api/benchmark/events/transcript", payload)
        except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
            self._warn_publish_failed(exc)

    def _post_json(self, path: str, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            response.read()

    def _warn_publish_failed(self, exc: Exception) -> None:
        now = time.monotonic()
        if now - self._last_warning_at < 60.0:
            return
        self._last_warning_at = now
        logger.warning(
            "benchmark API publish failed; continuing without dashboard event publish "
            "base_url=%s error=%s",
            self.base_url,
            exc,
        )
