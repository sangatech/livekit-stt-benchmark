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
Running upgrade 20260507_0001 -> 20260508_0002, reference transcripts
```

Verify:

```bash
python -m alembic current
```

Expected:

```text
20260508_0002 (head)
```

## Run Backend And UI

The UI and backend are served by the same FastAPI app.

Start the dashboard service:

```bash
python -m uvicorn api.benchmark_app:app --host 0.0.0.0 --port 8090
```

Or use the repo script:

```bash
./scripts/run_dashboard.sh
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
- Call reference turns API: `/api/benchmark/calls/{call_id}/turns`
- All-calls WER API: `/api/benchmark/wer/summary`
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

Or use the repo script:

```bash
./scripts/run_agent.sh
```

Restart the voice agent after changing benchmark code or `.env`. Calls that happened before the agent was restarted will not appear in the dashboard because transcript events were not being published yet.

## Run On Server With systemd

Recommended for a Linux server.

1. Install dependencies:

```bash
python -m venv venv
./venv/bin/python -m pip install -r requirements.txt
```

2. Confirm `.env` is configured and migrations are applied:

```bash
./venv/bin/python -m alembic upgrade head
```

3. Install systemd services:

```bash
sudo APP_DIR="$(pwd)" SERVICE_USER="$(whoami)" SERVICE_GROUP="$(id -gn)" ./scripts/install_systemd.sh
```

4. Start both services:

```bash
sudo systemctl start sangahub-stt-dashboard sangahub-stt-agent
```

5. Check status:

```bash
sudo systemctl status sangahub-stt-dashboard
sudo systemctl status sangahub-stt-agent
```

6. Follow logs:

```bash
journalctl -u sangahub-stt-dashboard -f
journalctl -u sangahub-stt-agent -f
```

Project log files:

```bash
tail -f logs/dashboard.log
tail -f logs/dashboard-error.log
tail -f logs/agent.log
tail -f logs/agent-error.log
```

7. Restart after deploy or `.env` changes:

```bash
sudo systemctl restart sangahub-stt-dashboard sangahub-stt-agent
```

The dashboard listens on port `8090` by default.

## Run On Server With PM2

Use this if the server already uses PM2.

```bash
pm2 start deploy/pm2/ecosystem.config.cjs
pm2 save
```

Check logs:

```bash
pm2 logs stt-dashboard
pm2 logs stt-agent
```

PM2 also writes to project log files:

```bash
tail -f logs/dashboard.log
tail -f logs/dashboard-error.log
tail -f logs/dashboard-combined.log
tail -f logs/agent.log
tail -f logs/agent-error.log
tail -f logs/agent-combined.log
```

Restart:

```bash
pm2 restart stt-dashboard stt-agent
```

Stop:

```bash
pm2 stop stt-dashboard stt-agent
```

## Apache Reverse Proxy

Apache should proxy public traffic to the dashboard backend on `127.0.0.1:8090`.

Enable required Apache modules:

```bash
sudo a2enmod proxy proxy_http proxy_wstunnel headers rewrite ssl
sudo systemctl restart apache2
```

Install the vhost:

```bash
sudo cp deploy/apache/stt.sangahub.com.conf /etc/apache2/sites-available/stt.sangahub.com.conf
sudo a2ensite stt.sangahub.com.conf
sudo apachectl configtest
sudo systemctl reload apache2
```

The included vhost proxies:

```text
http://stt.sangahub.com/       -> http://127.0.0.1:8090/
ws://stt.sangahub.com/ws/...   -> ws://127.0.0.1:8090/ws/...
```

Enable HTTPS with Certbot:

```bash
sudo certbot --apache -d stt.sangahub.com
```

Apache logs:

```bash
sudo tail -f /var/log/apache2/stt.sangahub.com-access.log
sudo tail -f /var/log/apache2/stt.sangahub.com-error.log
```

## Direct Script Logs

By default, direct scripts print to the terminal:

```bash
./scripts/run_dashboard.sh
./scripts/run_agent.sh
```

To write direct script output to `logs/` instead:

```bash
LOG_TO_FILE=true ./scripts/run_dashboard.sh
LOG_TO_FILE=true ./scripts/run_agent.sh
```

Direct script log files:

```text
logs/dashboard.log
logs/dashboard-error.log
logs/agent.log
logs/agent-error.log
```

## Modes

## AgentSession Voice Settings

The agent uses English-only STT, LiveKit's English turn detector, BVC telephony
noise cancellation, endpointing, interruption, STT, TTS, and LLM wiring in
`AgentSession`. These voice settings are fixed in `agent.py`; the `Agent`
itself only carries `instruction.txt`.

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

## Human Reference WER

True WER requires a human reference transcript. Open a call in the dashboard,
review each finalized turn, type what the caller actually said in the Human
Reference WER section, and save it.

After references are saved, the dashboard shows:

- Per-turn WER for Deepgram and Speechmatics
- Per-call WER for Deepgram and Speechmatics
- All-calls aggregate WER for Deepgram and Speechmatics

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

If agent logs show benchmark publish failures with `Connection refused`, the
agent is running but the benchmark dashboard API is not reachable at
`BENCHMARK_API_URL`. Start the dashboard service, fix `BENCHMARK_API_URL`, or
set `BENCHMARK_PUBLISH_EVENTS=false` when you do not need dashboard events.

3. Restart the voice agent and place a new call.

If only the primary provider appears, confirm shadow mode is enabled and restart the agent:

```env
STT_BENCHMARK_MODE=shadow
STT_PRIMARY_PROVIDER=deepgram
STT_SHADOW_PROVIDER=speechmatics
```

In shadow/comparison mode, `agent.py` uses `BenchmarkingSTT` to tee the same audio frames to both providers. The primary provider still drives the conversation; the shadow provider only publishes benchmark events.
