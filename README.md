# LiveKit Voice Agent

A Python voice agent for LiveKit that uses AI to have natural conversations with users, supporting multiple STT (Speech-to-Text) providers.

## Features

- **Multi-STT Support**: Choose between Deepgram or Speechmatics for speech recognition
- **STT Benchmarking**: Optional production, shadow, and comparison modes for Deepgram vs Speechmatics
- **Real-time Dashboard**: FastAPI websocket dashboard for live transcripts, latency, and provider health
- **AI-Powered Conversations**: Uses OpenAI GPT models for intelligent responses
- **Instruction-Based Behavior**: Agent behavior controlled via `instruction.txt` file
- **English Voice Pipeline**: English STT, LiveKit English turn detection, Silero VAD, and BVC telephony noise cancellation
- **Environment-based Credentials**: `.env` is used for credentials, provider selection, model names, and benchmark settings
- **Latest LiveKit SDK**: Built with the latest LiveKit agents framework (v1.5.8+)

## Prerequisites

- Python 3.9 or higher
- LiveKit server (local or cloud)
- API keys for your chosen STT provider:
  - Deepgram API key (if using Deepgram)
  - Speechmatics API key (if using Speechmatics)
- OpenAI API key (for LLM and TTS)
- `livekit-plugins-noise-cancellation`, installed through `requirements.txt`

## Installation

1. **Clone or navigate to the project directory**

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Configure environment variables**:
```bash
cp .env.example .env
```

Edit `.env` and add your credentials:
```env
LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret

# Choose your STT provider
STT_PROVIDER=deepgram  # or 'speechmatics'

# Deepgram configuration (if using Deepgram)
DEEPGRAM_API_KEY=your_deepgram_api_key
DEEPGRAM_STT_MODEL=nova-3

# Speechmatics configuration (if using Speechmatics)
SPEECHMATICS_API_KEY=your_speechmatics_api_key
SPEECHMATICS_OPERATING_POINT=enhanced

# OpenAI for LLM and TTS
OPENAI_API_KEY=your_openai_api_key
OPENAI_LLM_MODEL=gpt-4o-mini
OPENAI_TTS_MODEL=tts-1
OPENAI_TTS_VOICE=alloy
```

## Usage

### Running the Agent

Start the agent with:
```bash
python agent.py dev
```

For production:
```bash
python agent.py start
```

### Switching STT Providers

To switch between STT providers, simply change the `STT_PROVIDER` value in your `.env` file:

- For Deepgram: `STT_PROVIDER=deepgram`
- For Speechmatics: `STT_PROVIDER=speechmatics`

Make sure the corresponding API key is set in the `.env` file.

## How It Works

1. The agent connects to a LiveKit room
2. Loads instructions from `instruction.txt` file
3. Waits for a participant to join
4. Uses the configured STT provider (Deepgram or Speechmatics) to transcribe speech
5. Uses fixed English turn handling, Silero VAD, and BVC telephony noise cancellation
6. Processes the transcription with OpenAI GPT model based on the instructions
7. Responds using OpenAI TTS
8. Continues the conversation naturally

## Customizing Agent Behavior

The agent's personality and behavior are controlled by the `instruction.txt` file. Simply edit this file to change how your agent behaves:

```bash
# Edit the instruction file
nano instruction.txt
```

Example instructions:
- **Customer Support**: "You are a helpful customer support agent for XYZ company..."
- **Tutor**: "You are a patient tutor helping students learn mathematics..."
- **Assistant**: "You are a personal assistant helping with scheduling and tasks..."

The agent will follow whatever instructions you provide in this file.

## Project Structure

```
testbot/
├── agent.py              # Main agent implementation
├── instruction.txt       # Agent behavior instructions (customize this!)
├── requirements.txt      # Python dependencies
├── .env.example         # Environment variables template
├── .env                 # Your actual configuration (not in git)
└── README.md            # This file
```

## Configuration Options

### Session Configuration

The agent uses an optimized session configuration similar to IT_Curves_Bot:

- **English Turn Detection**: LiveKit `EnglishModel()` is used directly in code
- **Interruption Handling**: Allows natural interruptions with smart thresholds
- **VAD (Voice Activity Detection)**: Silero VAD with 0.6s minimum silence duration
- **Endpointing**: Fixed delays (0.5s min, 4.0s max) for natural conversation flow
- **Interruption Thresholds**: 0.8s duration minimum, at least 1 word required
- **Noise Cancellation**: LiveKit BVC telephony noise cancellation via `RoomInputOptions`

These voice settings are fixed in `agent.py`; they are not configured through `.env`.

### STT Providers

**Deepgram**:
- Fast and accurate
- English language configured in code
- Real-time streaming
- Models: `nova-2`, `nova-3`, `nova-2-general`, etc.

**Speechmatics**:
- High accuracy
- English language configured in code
- Custom vocabulary support
- Operating points: `enhanced` (recommended) or `standard`

Both providers receive the IT_Curves domain keyterms from `stt/keyterms.json`.
Deepgram uses its native `keyterms` option; Speechmatics uses `additional_vocab`.

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `LIVEKIT_URL` | LiveKit server URL | - | Yes |
| `LIVEKIT_API_KEY` | LiveKit API key | - | Yes |
| `LIVEKIT_API_SECRET` | LiveKit API secret | - | Yes |
| `STT_PROVIDER` | STT provider (`deepgram` or `speechmatics`) | `deepgram` | Yes |
| `DEEPGRAM_API_KEY` | Deepgram API key | - | If using Deepgram |
| `DEEPGRAM_STT_MODEL` | Deepgram model | `nova-2` | No |
| `SPEECHMATICS_API_KEY` | Speechmatics API key | - | If using Speechmatics |
| `SPEECHMATICS_OPERATING_POINT` | Speechmatics quality (`enhanced` or `standard`) | `enhanced` | No |
| `OPENAI_API_KEY` | OpenAI API key for LLM and TTS | - | Yes |
| `OPENAI_LLM_MODEL` | OpenAI model for conversations | `gpt-4o-mini` | No |
| `OPENAI_TTS_MODEL` | OpenAI TTS model | `tts-1` | No |
| `OPENAI_TTS_VOICE` | OpenAI TTS voice | `alloy` | No |

### STT Benchmarking

The original production path remains single-provider. Enable benchmarking with feature flags:

```env
STT_BENCHMARK_MODE=shadow       # production, shadow, or comparison
STT_PRIMARY_PROVIDER=deepgram
STT_SHADOW_PROVIDER=speechmatics
BENCHMARK_DATABASE_URL=postgresql+psycopg://benchmark:benchmark@localhost:5432/benchmark
BENCHMARK_API_URL=http://127.0.0.1:8090
BENCHMARK_PUBLISH_EVENTS=true
BENCHMARK_STORAGE_ROOT=calls
BENCHMARK_S3_BUCKET=
```

Run the dashboard:

```bash
uvicorn api.benchmark_app:app --host 0.0.0.0 --port 8080
```

Apply the PostgreSQL migration:

```bash
alembic upgrade head
```

Dashboard endpoints:

- `/` live dashboard
- `/ws/benchmark/live`
- `/ws/call/{id}`
- `/ws/provider-stats`
- `/api/benchmark/calls/{call_id}/turns` human reference turn review
- `/api/benchmark/wer/summary` all-calls WER summary

### Human Reference WER

The dashboard includes a Human Reference WER section for the selected call.
Type the full correct caller transcript for the call and save it. Provider
finals are concatenated before WER is calculated, so a provider that splits one
sentence into two finals can still score correctly at call level.

After a reference is saved, the dashboard calculates:

- Deepgram call-level WER
- Speechmatics call-level WER
- Aggregate all-calls WER for each provider
- Final segment counts per provider, so you can see which provider split the
  same speech into one, two, or more final segments

Architecture and rollout details are in `docs/stt_benchmark_architecture.md`.

Operational run commands are in `docs/runbook.md`.

## Troubleshooting

### Missing API Key Error
If you see an error about missing API keys, ensure:
1. Your `.env` file exists and is in the same directory as `agent.py`
2. The API key for your chosen STT provider is set
3. The `STT_PROVIDER` value matches your configured provider

### Connection Issues
- Verify your LiveKit server is running
- Check that `LIVEKIT_URL` is correct
- Ensure your API key and secret are valid

### Benchmark Publish Connection Refused
If the agent logs `benchmark API publish failed` or `Connection refused`, the
dashboard API is not reachable at `BENCHMARK_API_URL`. Start the dashboard,
correct `BENCHMARK_API_URL`, or set `BENCHMARK_PUBLISH_EVENTS=false` when you
do not need benchmark dashboard events.

## License

MIT
