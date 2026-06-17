from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

from benchmark.settings import setting

from .base_provider import STTProvider
from .deepgram_provider import DeepgramProvider
from .soniox_provider import SonioxProvider
from .speechmatics_provider import SpeechmaticsProvider


class BenchmarkMode(str, Enum):
    PRODUCTION = "production"
    SHADOW = "shadow"
    COMPARISON = "comparison"


PROVIDERS: dict[str, type[STTProvider]] = {
    "deepgram": DeepgramProvider,
    "soniox": SonioxProvider,
    "speechmatics": SpeechmaticsProvider,
}

PROVIDER_ALIASES = {
    "seniox": "soniox",
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
        mode = BenchmarkMode(str(setting("stt_benchmark_mode", os.getenv("STT_BENCHMARK_MODE", "production"))).lower())
        primary_name = _normalize_provider_name(
            str(setting("stt_primary_provider", os.getenv("STT_PRIMARY_PROVIDER", os.getenv("STT_PROVIDER", "deepgram"))))
        )
        secondary_name = _normalize_provider_name(str(setting("stt_shadow_provider", os.getenv("STT_SHADOW_PROVIDER", ""))))

        if not secondary_name:
            secondary_name = "speechmatics" if primary_name == "deepgram" else "deepgram"

        primary = self._build(primary_name, role="primary")
        secondary = None if mode == BenchmarkMode.PRODUCTION else self._build(secondary_name, role="shadow")
        _label_provider_variant(primary, role="primary")
        if secondary is not None:
            _label_provider_variant(secondary, role="shadow")
            if primary.provider_name == secondary.provider_name:
                _label_provider_variant(primary, role="primary", include_role=True)
                _label_provider_variant(secondary, role="shadow", include_role=True)
        return ProviderSelection(mode=mode, primary=primary, secondary=secondary)

    def _build(self, provider_name: str, *, role: str) -> STTProvider:
        provider_name = _normalize_provider_name(provider_name)
        try:
            provider_cls = PROVIDERS[provider_name]
        except KeyError as exc:
            supported = ", ".join(sorted(PROVIDERS))
            raise ValueError(f"Unknown STT provider: {provider_name}. Use one of: {supported}") from exc
        return provider_cls(call_id=self.call_id, room_id=self.room_id, role=role)


def _normalize_provider_name(provider_name: str) -> str:
    normalized = provider_name.strip().lower()
    return PROVIDER_ALIASES.get(normalized, normalized)


def _label_provider_variant(provider: STTProvider, *, role: str, include_role: bool = False) -> None:
    base_name = getattr(provider, "base_provider_name", provider.provider_name.split(":", 1)[0])
    variant = getattr(provider, "model", None) or getattr(provider, "operating_point", None) or role
    suffix = f"{role}-{variant}" if include_role else variant
    provider.provider_name = f"{base_name}:{suffix}"
