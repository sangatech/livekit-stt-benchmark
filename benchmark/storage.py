from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class BenchmarkStorage:
    def __init__(self, *, local_root: str = "calls") -> None:
        self.local_root = Path(os.getenv("BENCHMARK_STORAGE_ROOT", local_root))
        self.s3_bucket = os.getenv("BENCHMARK_S3_BUCKET")

    def write_json(self, call_id: str, name: str, payload: Any) -> str:
        path = self.local_root / call_id / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if self.s3_bucket:
            return self._upload(path, call_id, name)
        return str(path)

    def write_bytes(self, call_id: str, name: str, payload: bytes) -> str:
        path = self.local_root / call_id / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        if self.s3_bucket:
            return self._upload(path, call_id, name)
        return str(path)

    def _upload(self, path: Path, call_id: str, name: str) -> str:
        import boto3

        key = f"calls/{call_id}/{name}"
        boto3.client("s3").upload_file(str(path), self.s3_bucket, key)
        return f"s3://{self.s3_bucket}/{key}"
