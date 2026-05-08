from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

from .base_provider import STTProvider
from .deepgram_provider import DeepgramProvider
from .speechmatics_provider import SpeechmaticsProvider


class BenchmarkMode(str, Enum):
    PRODUCTION = "production"
    SHADOW = "shadow"
    COMPARISON = "comparison"


PROVIDERS: dict[str, type[STTProvider]] = {
    "deepgram": DeepgramProvider,
    "speechmatics": SpeechmaticsProvider,
}


@dataclass(frozen=True)
class ProviderSelection:
    mode: BenchmarkMode
    primary: STTProvider
    secondary: STTProvider | None

    @property
    def active_providers(self) -> list[STTProvider]:
        providers = [self.primary]
        if self.secondary is not None:
            providers.append(self.secondary)
        return providers


class STTProviderManager:
    def __init__(self, *, call_id: str | None = None, room_id: str | None = None) -> None:
        self.call_id = call_id
        self.room_id = room_id

    def select(self) -> ProviderSelection:
        mode = BenchmarkMode(os.getenv("STT_BENCHMARK_MODE", "production").lower())
        primary_name = os.getenv("STT_PRIMARY_PROVIDER", os.getenv("STT_PROVIDER", "deepgram")).lower()
        secondary_name = os.getenv("STT_SHADOW_PROVIDER", "").lower()

        if not secondary_name:
            secondary_name = "speechmatics" if primary_name == "deepgram" else "deepgram"

        primary = self._build(primary_name)
        secondary = None if mode == BenchmarkMode.PRODUCTION else self._build(secondary_name)
        return ProviderSelection(mode=mode, primary=primary, secondary=secondary)

    def _build(self, provider_name: str) -> STTProvider:
        try:
            provider_cls = PROVIDERS[provider_name]
        except KeyError as exc:
            supported = ", ".join(sorted(PROVIDERS))
            raise ValueError(f"Unknown STT provider: {provider_name}. Use one of: {supported}") from exc
        return provider_cls(call_id=self.call_id, room_id=self.room_id)
