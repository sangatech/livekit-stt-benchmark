# Runbook

## Prerequisites

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Configure `.env`:

```env
BENCHMARK_DATABASE_URL=postgresql+psycopg://benchmark:URL_ENCODED_PASSWORD@YOUR_DB_HOST:5432/benchmark
BENCHMARK_API_URL=http://127.0.0.1:8090
BENCHMARK_PUBLISH_EVENTS=true
STT_BENCHMARK_MODE=shadow
STT_PRIMARY_PROVIDER=deepgram
STT_SHADOW_PROVIDER=speechmatics
```

If a password contains special characters, URL-encode them. For example, `@` becomes `%40`.

## Run Database Migrations

Check the current migration:

```bash
python -m alembic current
```

Apply migrations:

```bash
python -m alembic upgrade head
```

Expected success output includes:

```text
Running upgrade  -> 20260507_0001, benchmark schema
```

Verify:

```bash
python -m alembic current
```

Expected:

```text
20260507_0001 (head)
```

## Run Backend And UI

The UI and backend are served by the same FastAPI app.

Start the dashboard service:

```bash
python -m uvicorn api.benchmark_app:app --host 0.0.0.0 --port 8090
```

Open:

```text
http://127.0.0.1:8090
```

If running on a remote server, open:

```text
http://YOUR_SERVER_IP:8090
```

## Verify Backend

Health-check the calls API:

```bash
curl http://127.0.0.1:8090/api/benchmark/calls
```

Expected when no calls are active:

```json
[]
```

Main endpoints:

- UI: `/`
- Calls API: `/api/benchmark/calls`
- Call detail API: `/api/benchmark/calls/{call_id}`
- Live websocket: `/ws/benchmark/live`
- Call websocket: `/ws/call/{call_id}`
- Provider stats websocket: `/ws/provider-stats`

## Run Voice Agent

In a separate terminal:

```bash
python agent.py dev
```

Production:

```bash
python agent.py start
```

Restart the voice agent after changing benchmark code or `.env`. Calls that happened before the agent was restarted will not appear in the dashboard because transcript events were not being published yet.

## Modes

Production mode:

```env
STT_BENCHMARK_MODE=production
STT_PROVIDER=deepgram
```

Shadow mode:

```env
STT_BENCHMARK_MODE=shadow
STT_PRIMARY_PROVIDER=deepgram
STT_SHADOW_PROVIDER=speechmatics
```

Comparison mode:

```env
STT_BENCHMARK_MODE=comparison
STT_PRIMARY_PROVIDER=deepgram
STT_SHADOW_PROVIDER=speechmatics
```

## Docker Option

Start Postgres and dashboard:

```bash
docker compose -f docker-compose.benchmark.yml up -d
```

Run migrations from the host:

```bash
python -m alembic upgrade head
```

Open:

```text
http://127.0.0.1:8080
```

## Troubleshooting

If Alembic cannot resolve the host, the database URL is malformed. Check it without printing the password:

```bash
python - <<'PY'
from pathlib import Path
from dotenv import dotenv_values
from sqlalchemy.engine import make_url
url = make_url(dotenv_values(Path(".env"))["BENCHMARK_DATABASE_URL"])
print(url.drivername, url.host, url.port, url.database, url.username, bool(url.password))
PY
```

If the host is wrong, URL-encode the password.

If Alembic cannot connect but the URL parses correctly, check PostgreSQL network access:

```bash
pg_isready -h YOUR_DB_HOST -p 5432 -d benchmark -U benchmark
```

If calls do not appear in the UI:

1. Confirm the dashboard is running:

```bash
curl http://127.0.0.1:8090/api/benchmark/calls
```

2. Confirm the agent has these variables:

```env
BENCHMARK_API_URL=http://127.0.0.1:8090
BENCHMARK_PUBLISH_EVENTS=true
```

3. Restart the voice agent and place a new call.

If only the primary provider appears, confirm shadow mode is enabled and restart the agent:

```env
STT_BENCHMARK_MODE=shadow
STT_PRIMARY_PROVIDER=deepgram
STT_SHADOW_PROVIDER=speechmatics
```

In shadow/comparison mode, `agent.py` uses `BenchmarkingSTT` to tee the same audio frames to both providers. The primary provider still drives the conversation; the shadow provider only publishes benchmark events.
