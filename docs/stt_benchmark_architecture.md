# STT Benchmark Architecture

## Repository Findings

- LiveKit integration is in `agent.py`, via `JobContext`, `ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)`, and `AgentSession`.
- STT selection was a single function returning exactly one provider object for `AgentSession(stt=stt, ...)`.
- The current production voice flow is LiveKit Agents managed audio with fixed English turn detection, Silero VAD, BVC telephony noise cancellation, STT, LLM, and TTS. There was no custom FastAPI server, frontend, database ORM, Alembic setup, or observability pipeline.
- Existing provider support was switch-based: `STT_PROVIDER=deepgram` or `STT_PROVIDER=speechmatics`.
- The only hard single-provider assumptions were `get_stt_provider()` and the single `stt=` argument passed into `AgentSession`.

## Migration Plan

1. Keep the primary LiveKit `AgentSession` path single-provider and stable.
2. Introduce provider objects with a shared transcript event schema.
3. Add `STT_BENCHMARK_MODE=production|shadow|comparison`.
4. In production mode, behavior remains equivalent to the original flow.
5. In shadow or comparison mode, the primary provider still drives the AI response while mirrored provider streams feed the benchmark engine.
6. Persist benchmark events and summaries locally first, then enable PostgreSQL and S3.
7. Run the dashboard as a separate FastAPI service so agent latency and dashboard load are isolated.

## Runtime Diagram

```text
LiveKit Audio Track
        |
        v
LiveKit AgentSession
   EnglishModel turn detection
   Silero VAD
   BVC telephony noise cancellation
        |
        v
BenchmarkingSTT tee
   |              |
   v              v
Deepgram      Speechmatics
   |              |
   v              v
Provider-normalized transcript events
        |
        v
Benchmark Engine -> PostgreSQL / local calls/{call_id}/ / S3
        |
        v
FastAPI WebSockets -> Dashboard
        |
        v
Human reference turns -> provider WER per call and across all calls

Only the primary STT stream is returned to `AgentSession` for LLM/TTS turn handling.
The shadow stream is silent and only feeds benchmark storage/UI.
```

## Human Reference WER

Final transcripts are paired by provider final-turn order. A reviewer enters
the human reference transcript for each turn in the dashboard. WER is then
computed separately for each provider against that saved reference transcript,
and aggregate WER is computed across all reviewed turns.

## Modes

- `production`: one STT provider only. The dashboard can run, but no mirrored provider is created.
- `shadow`: primary provider drives the AI. Secondary provider runs silently for metrics.
- `comparison`: both providers are active and visible in the dashboard.

## Rollout Strategy

1. Deploy dashboard and database with `STT_BENCHMARK_MODE=production`.
2. Enable local persistence with a small internal traffic slice.
3. Enable `shadow` with `STT_PRIMARY_PROVIDER=deepgram` and `STT_SHADOW_PROVIDER=speechmatics`.
4. Watch p95 final latency, reconnects, partial rewrite frequency, and dashboard websocket health.
5. Reverse primary and shadow providers for an equivalent traffic window.
6. Use `comparison` only in controlled sessions where live transcript visibility is desired.

## Environment

```env
STT_BENCHMARK_MODE=shadow
STT_PRIMARY_PROVIDER=deepgram
STT_SHADOW_PROVIDER=speechmatics
BENCHMARK_DATABASE_URL=postgresql+psycopg://benchmark:benchmark@postgres:5432/benchmark
BENCHMARK_STORAGE_ROOT=calls
BENCHMARK_S3_BUCKET=
```

## Dashboard

Run:

```bash
uvicorn api.benchmark_app:app --host 0.0.0.0 --port 8080
```

Websocket endpoints:

- `/ws/benchmark/live`
- `/ws/call/{id}`
- `/ws/provider-stats`

REST endpoints:

- `/api/benchmark/calls`
- `/api/benchmark/calls/{call_id}`
- `/api/benchmark/events/transcript`
