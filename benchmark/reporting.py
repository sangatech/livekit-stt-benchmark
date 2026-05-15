from __future__ import annotations

import html
from dataclasses import asdict, dataclass
from datetime import datetime
from statistics import mean
from typing import Any


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
    scorecards = [asdict(provider_scorecard(value)) for value in providers.values()]
    return {
        "call_id": summary.get("call_id"),
        "room_id": summary.get("room_id"),
        "duration_s": summary.get("duration_s"),
        "scorecards": scorecards,
        "comparison": summary.get("comparison"),
        "latency_percentiles": metrics.get("latency_percentiles", {}) if isinstance(metrics, dict) else {},
    }


def build_call_report_data(
    *,
    call_detail: dict[str, object],
    call_turns: dict[str, object],
    all_calls_wer: dict[str, object],
) -> dict[str, object]:
    events = list(call_detail.get("events") or [])
    provider_metrics = _provider_metrics(events)
    call_provider_wer = call_turns.get("call_provider_wer") or {}
    call_provider_segments = call_turns.get("call_provider_segments") or {}
    all_calls_providers = all_calls_wer.get("providers") or {}

    providers = sorted(set(provider_metrics) | set(call_provider_wer) | set(call_provider_segments))
    scorecards = [
        _report_provider(
            provider=provider,
            metrics=provider_metrics.get(provider, {}),
            call_wer=call_provider_wer.get(provider, {}),
            all_calls_wer=all_calls_providers.get(provider, {}),
            final_segments=call_provider_segments.get(provider),
        )
        for provider in providers
    ]

    return {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "call_id": call_detail.get("call_id"),
        "room_id": call_detail.get("room_id"),
        "started_at": call_detail.get("started_at"),
        "ended_at": call_detail.get("ended_at"),
        "event_count": len(events),
        "final_event_count": len([event for event in events if event.get("is_final")]),
        "has_reference": bool(str(call_turns.get("call_reference_transcript") or "").strip()),
        "providers": scorecards,
        "winners": _winners(scorecards),
        "all_calls_wer": all_calls_wer,
        "reference_transcript": call_turns.get("call_reference_transcript") or "",
        "provider_transcripts": call_turns.get("call_provider_transcripts") or {},
    }


def render_call_report_html(report: dict[str, object]) -> str:
    providers = list(report.get("providers") or [])
    winners = report.get("winners") or {}
    reference_note = (
        "WER is calculated against the saved human reference transcript."
        if report.get("has_reference")
        else "No human reference transcript has been saved for this call, so WER is not available."
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>STT Benchmark Report</title>
  <style>
    :root {{
      color: #18181b;
      background: #f4f4f5;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    body {{ margin: 0; }}
    .page {{ max-width: 1120px; margin: 0 auto; padding: 40px 28px; }}
    .hero {{ background: #101827; color: #fff; border-radius: 10px; padding: 30px; }}
    .eyebrow {{ color: #93c5fd; font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }}
    h1 {{ margin: 8px 0 10px; font-size: 30px; line-height: 1.15; }}
    h2 {{ margin: 0 0 14px; font-size: 17px; }}
    h3 {{ margin: 0; font-size: 14px; }}
    .subtle {{ color: #d4d4d8; font-size: 13px; line-height: 1.6; }}
    .grid {{ display: grid; gap: 14px; }}
    .summary {{ grid-template-columns: repeat(4, minmax(0, 1fr)); margin-top: 18px; }}
    .cards {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
    .tile, .section {{ background: #fff; border: 1px solid #e4e4e7; border-radius: 10px; padding: 18px; }}
    .tile-label {{ color: #71717a; font-size: 11px; font-weight: 700; text-transform: uppercase; }}
    .tile-value {{ margin-top: 6px; font-size: 20px; font-weight: 750; }}
    .section {{ margin-top: 18px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th {{ color: #52525b; text-align: left; font-size: 11px; text-transform: uppercase; border-bottom: 1px solid #e4e4e7; padding: 10px 8px; }}
    td {{ border-bottom: 1px solid #f1f1f3; padding: 11px 8px; vertical-align: top; }}
    .provider {{ font-weight: 750; }}
    .score {{ display: inline-block; min-width: 52px; border-radius: 999px; padding: 4px 9px; text-align: center; font-weight: 750; background: #dcfce7; color: #166534; }}
    .muted {{ color: #71717a; }}
    .transcript {{ max-height: 220px; overflow: auto; white-space: pre-wrap; background: #fafafa; border: 1px solid #e4e4e7; border-radius: 8px; padding: 12px; font-size: 12px; line-height: 1.55; }}
    .actions {{ margin-top: 18px; display: flex; justify-content: flex-end; }}
    button {{ border: 0; border-radius: 8px; background: #2563eb; color: #fff; padding: 10px 14px; font-weight: 700; cursor: pointer; }}
    @media print {{
      :root {{ background: #fff; }}
      .page {{ padding: 0; }}
      .hero, .tile, .section {{ break-inside: avoid; }}
      .actions {{ display: none; }}
    }}
    @media (max-width: 900px) {{
      .summary, .cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 640px) {{
      .summary, .cards {{ grid-template-columns: 1fr; }}
      .page {{ padding: 18px; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <div class="eyebrow">STT Benchmark Report</div>
      <h1>{_e(report.get("call_id") or "Selected Call")}</h1>
      <div class="subtle">
        Room: {_e(report.get("room_id") or "n/a")} · Generated: {_e(report.get("generated_at"))}<br />
        {html.escape(reference_note)}
      </div>
      <div class="grid summary">
        {_tile("Best WER", _e(winners.get("wer") or "n/a"), "Lowest call-level WER")}
        {_tile("Fastest", _e(winners.get("latency") or "n/a"), "Lowest average latency")}
        {_tile("Most Stable", _e(winners.get("stability") or "n/a"), "Highest partial stability")}
        {_tile("Final Segments", _e(report.get("final_event_count")), "Total final STT events")}
      </div>
    </section>

    <section class="section">
      <h2>Provider Performance</h2>
      <table>
        <thead>
          <tr>
            <th>Provider</th>
            <th>Score</th>
            <th>Call WER</th>
            <th>All-Calls WER</th>
            <th>Avg Latency</th>
            <th>First Final</th>
            <th>Stability</th>
            <th>Finals</th>
          </tr>
        </thead>
        <tbody>
          {''.join(_provider_row(provider) for provider in providers) or '<tr><td colspan="8" class="muted">No provider events available.</td></tr>'}
        </tbody>
      </table>
    </section>

    <section class="section">
      <h2>Executive Summary</h2>
      <div class="grid cards">
        {_insight("Accuracy", _accuracy_insight(providers, report))}
        {_insight("Latency", _latency_insight(providers))}
        {_insight("Streaming Quality", _stability_insight(providers))}
      </div>
    </section>

    <section class="section">
      <h2>Call Reference</h2>
      <div class="transcript">{_e(report.get("reference_transcript") or "No human reference transcript saved.")}</div>
    </section>

    <section class="section">
      <h2>Provider Final Transcripts</h2>
      {''.join(_transcript_block(provider, text) for provider, text in sorted((report.get("provider_transcripts") or {}).items())) or '<div class="muted">No final provider transcripts available.</div>'}
    </section>

    <div class="actions"><button onclick="window.print()">Print or Save as PDF</button></div>
  </main>
</body>
</html>"""


def _provider_metrics(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}
    for event in events:
        provider = str(event.get("provider") or "unknown")
        stats = metrics.setdefault(
            provider,
            {
                "provider": provider,
                "events": 0,
                "partial_events": 0,
                "final_events": 0,
                "latencies": [],
                "confidences": [],
                "partial_rewrites": 0,
                "last_partial": "",
                "first_partial_latency_ms": None,
                "first_final_latency_ms": None,
            },
        )
        stats["events"] += 1
        latency = event.get("latency_ms")
        if latency is not None:
            stats["latencies"].append(float(latency))
        confidence = event.get("confidence")
        if confidence is not None:
            stats["confidences"].append(float(confidence))
        if event.get("is_final"):
            stats["final_events"] += 1
            if stats["first_final_latency_ms"] is None and latency is not None:
                stats["first_final_latency_ms"] = float(latency)
        else:
            stats["partial_events"] += 1
            transcript = str(event.get("transcript") or "")
            if stats["last_partial"] and stats["last_partial"] != transcript:
                stats["partial_rewrites"] += 1
            stats["last_partial"] = transcript
            if stats["first_partial_latency_ms"] is None and latency is not None:
                stats["first_partial_latency_ms"] = float(latency)
    for stats in metrics.values():
        stats["avg_latency_ms"] = mean(stats["latencies"]) if stats["latencies"] else None
        stats["avg_confidence"] = mean(stats["confidences"]) if stats["confidences"] else None
        partial_events = int(stats["partial_events"])
        stats["transcript_stability"] = max(0.0, 1 - (int(stats["partial_rewrites"]) / partial_events)) if partial_events else 1.0
    return metrics


def _report_provider(
    *,
    provider: str,
    metrics: dict[str, Any],
    call_wer: dict[str, Any],
    all_calls_wer: dict[str, Any],
    final_segments: Any,
) -> dict[str, Any]:
    wer = call_wer.get("wer")
    latency = metrics.get("avg_latency_ms")
    stability = float(metrics.get("transcript_stability", 1.0))
    confidence = metrics.get("avg_confidence")
    wer_score = 0.75 if wer is None else max(0.0, 1.0 - float(wer))
    latency_score = 1.0 if latency is None else max(0.0, 1.0 - (float(latency) / 3000.0))
    confidence_score = 0.75 if confidence is None else float(confidence)
    score = round(((wer_score * 0.45) + (latency_score * 0.25) + (stability * 0.2) + (confidence_score * 0.1)) * 100, 1)
    return {
        "provider": provider,
        "score": score,
        "call_wer": wer,
        "all_calls_wer": all_calls_wer.get("wer"),
        "avg_latency_ms": latency,
        "first_partial_latency_ms": metrics.get("first_partial_latency_ms"),
        "first_final_latency_ms": metrics.get("first_final_latency_ms"),
        "transcript_stability": stability,
        "avg_confidence": confidence,
        "events": metrics.get("events", 0),
        "final_events": metrics.get("final_events", final_segments or 0),
        "partial_rewrites": metrics.get("partial_rewrites", 0),
    }


def _winners(providers: list[dict[str, Any]]) -> dict[str, str]:
    return {
        "wer": _winner(providers, "call_wer", lower=True),
        "latency": _winner(providers, "avg_latency_ms", lower=True),
        "stability": _winner(providers, "transcript_stability", lower=False),
    }


def _winner(providers: list[dict[str, Any]], key: str, *, lower: bool) -> str:
    comparable = [provider for provider in providers if provider.get(key) is not None]
    if not comparable:
        return "n/a"
    comparable.sort(key=lambda provider: float(provider[key]), reverse=not lower)
    return str(comparable[0]["provider"]).title()


def _provider_row(provider: dict[str, Any]) -> str:
    return f"""
      <tr>
        <td class="provider">{_e(str(provider.get("provider") or "").title())}</td>
        <td><span class="score">{_e(provider.get("score"))}</span></td>
        <td>{_percent(provider.get("call_wer"))}</td>
        <td>{_percent(provider.get("all_calls_wer"))}</td>
        <td>{_ms(provider.get("avg_latency_ms"))}</td>
        <td>{_ms(provider.get("first_final_latency_ms"))}</td>
        <td>{_percent(provider.get("transcript_stability"))}</td>
        <td>{_e(provider.get("final_events"))}</td>
      </tr>
    """


def _accuracy_insight(providers: list[dict[str, Any]], report: dict[str, Any]) -> str:
    if not report.get("has_reference"):
        return "Add a human reference transcript to unlock call-level WER and make this report accuracy-complete."
    winner = _winner(providers, "call_wer", lower=True)
    return f"{winner} produced the lowest word error rate for this reviewed call."


def _latency_insight(providers: list[dict[str, Any]]) -> str:
    winner = _winner(providers, "avg_latency_ms", lower=True)
    return "Latency data is unavailable." if winner == "n/a" else f"{winner} had the lowest average transcript event latency."


def _stability_insight(providers: list[dict[str, Any]]) -> str:
    winner = _winner(providers, "transcript_stability", lower=False)
    return "Stability data is unavailable." if winner == "n/a" else f"{winner} had the most stable interim transcript stream."


def _insight(title: str, text: str) -> str:
    return f'<div class="tile"><div class="tile-label">{_e(title)}</div><div style="margin-top:8px;font-size:13px;line-height:1.55">{_e(text)}</div></div>'


def _tile(label: str, value: str, hint: str) -> str:
    return f'<div class="tile"><div class="tile-label">{_e(label)}</div><div class="tile-value">{value}</div><div class="muted" style="margin-top:5px;font-size:12px">{_e(hint)}</div></div>'


def _transcript_block(provider: str, text: str) -> str:
    return f'<h3 style="margin-top:16px">{_e(provider.title())}</h3><div class="transcript">{_e(text or "No transcript available.")}</div>'


def _percent(value: Any) -> str:
    return "n/a" if value is None else f"{float(value) * 100:.1f}%"


def _ms(value: Any) -> str:
    return "n/a" if value is None else f"{float(value):.0f} ms"


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value))
