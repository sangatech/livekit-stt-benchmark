from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ProviderScorecard:
    provider: str
    avg_latency_ms: float | None
    avg_confidence: float | None
    transcript_stability: float
    reconnects: int
    disconnects: int
    score: float


def provider_scorecard(provider_metrics: dict[str, object]) -> ProviderScorecard:
    latency = provider_metrics.get("avg_final_latency_ms")
    confidence = provider_metrics.get("avg_confidence")
    stability = float(provider_metrics.get("transcript_stability") or 0.0)
    reconnects = int(provider_metrics.get("reconnects") or 0)
    disconnects = int(provider_metrics.get("disconnects") or 0)
    latency_score = 1.0 if latency is None else max(0.0, 1.0 - (float(latency) / 3000.0))
    confidence_score = float(confidence) if confidence is not None else 0.7
    reliability_score = max(0.0, 1.0 - ((reconnects + disconnects) * 0.05))
    score = round(((latency_score * 0.35) + (confidence_score * 0.25) + (stability * 0.25) + (reliability_score * 0.15)) * 100, 2)
    return ProviderScorecard(
        provider=str(provider_metrics["provider"]),
        avg_latency_ms=None if latency is None else float(latency),
        avg_confidence=None if confidence is None else float(confidence),
        transcript_stability=stability,
        reconnects=reconnects,
        disconnects=disconnects,
        score=score,
    )


def build_report(summary: dict[str, object]) -> dict[str, object]:
    metrics = summary.get("metrics", {})
    providers = metrics.get("providers", {}) if isinstance(metrics, dict) else {}
    scorecards = [provider_scorecard(value).__dict__ for value in providers.values()]
    return {
        "call_id": summary.get("call_id"),
        "room_id": summary.get("room_id"),
        "duration_s": summary.get("duration_s"),
        "scorecards": scorecards,
        "comparison": summary.get("comparison"),
        "latency_percentiles": metrics.get("latency_percentiles", {}) if isinstance(metrics, dict) else {},
    }
