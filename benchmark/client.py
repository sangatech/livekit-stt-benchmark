from __future__ import annotations

import asyncio
import json
import os
import urllib.request
from typing import Any


class BenchmarkHttpPublisher:
    def __init__(self, *, base_url: str | None = None, timeout_s: float = 2.0) -> None:
        self.base_url = (base_url or os.getenv("BENCHMARK_API_URL", "http://127.0.0.1:8090")).rstrip("/")
        self.timeout_s = timeout_s

    async def publish_transcript(self, payload: dict[str, Any]) -> None:
        await asyncio.to_thread(self._post_json, "/api/benchmark/events/transcript", payload)

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
