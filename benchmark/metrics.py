from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field

from stt.base_provider import STTTranscriptEvent


@dataclass(slots=True)
class ProviderMetrics:
    provider: str
    first_partial_latency_ms: float | None = None
    first_final_latency_ms: float | None = None
    final_latency_ms: list[float] = field(default_factory=list)
    partial_latency_ms: list[float] = field(default_factory=list)
    confidence_scores: list[float] = field(default_factory=list)
    partial_rewrites: int = 0
    final_events: int = 0
    partial_events: int = 0
    reconnects: int = 0
    disconnects: int = 0
    packet_loss_indicators: int = 0
    last_partial: str = ""
    last_final: str = ""

    def observe(self, event: STTTranscriptEvent) -> None:
        if event.confidence is not None:
            self.confidence_scores.append(float(event.confidence))
        if event.is_final:
            self.final_events += 1
            self.last_final = event.transcript
            if event.latency_ms is not None:
                self.final_latency_ms.append(event.latency_ms)
                self.first_final_latency_ms = self.first_final_latency_ms or event.latency_ms
        else:
            self.partial_events += 1
            if self.last_partial and self.last_partial != event.transcript:
                self.partial_rewrites += 1
            self.last_partial = event.transcript
            if event.latency_ms is not None:
                self.partial_latency_ms.append(event.latency_ms)
                self.first_partial_latency_ms = self.first_partial_latency_ms or event.latency_ms

    @property
    def transcript_stability(self) -> float:
        if self.partial_events == 0:
            return 1.0
        return max(0.0, 1.0 - (self.partial_rewrites / self.partial_events))

    def snapshot(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "first_partial_latency_ms": self.first_partial_latency_ms,
            "first_final_latency_ms": self.first_final_latency_ms,
            "avg_partial_latency_ms": mean_or_none(self.partial_latency_ms),
            "avg_final_latency_ms": mean_or_none(self.final_latency_ms),
            "p50_final_latency_ms": percentile(self.final_latency_ms, 50),
            "p95_final_latency_ms": percentile(self.final_latency_ms, 95),
            "avg_confidence": mean_or_none(self.confidence_scores),
            "partial_rewrites": self.partial_rewrites,
            "partial_events": self.partial_events,
            "final_events": self.final_events,
            "transcript_stability": self.transcript_stability,
            "reconnects": self.reconnects,
            "disconnects": self.disconnects,
            "packet_loss_indicators": self.packet_loss_indicators,
            "last_partial": self.last_partial,
            "last_final": self.last_final,
        }


class MetricsRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ProviderMetrics] = {}
        self._latency_by_provider: dict[str, list[float]] = defaultdict(list)

    def observe_transcript(self, event: STTTranscriptEvent) -> ProviderMetrics:
        metrics = self._providers.setdefault(event.provider, ProviderMetrics(provider=event.provider))
        metrics.observe(event)
        if event.latency_ms is not None:
            self._latency_by_provider[event.provider].append(event.latency_ms)
        return metrics

    def snapshot(self) -> dict[str, object]:
        return {
            "providers": {name: metrics.snapshot() for name, metrics in self._providers.items()},
            "latency_percentiles": {
                provider: {
                    "p50": percentile(values, 50),
                    "p90": percentile(values, 90),
                    "p95": percentile(values, 95),
                    "p99": percentile(values, 99),
                }
                for provider, values in self._latency_by_provider.items()
            },
        }


def mean_or_none(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def percentile(values: list[float], percent: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((percent / 100) * (len(ordered) - 1)))
    return ordered[index]
