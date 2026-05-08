# LiveKit Voice Agent

A Python voice agent for LiveKit that uses AI to have natural conversations with users, supporting multiple STT (Speech-to-Text) providers.

## Features

- **Multi-STT Support**: Choose between Deepgram or Speechmatics for speech recognition
- **STT Benchmarking**: Optional production, shadow, and comparison modes for Deepgram vs Speechmatics
- **Real-time Dashboard**: FastAPI websocket dashboard for live transcripts, latency, and provider health
- **AI-Powered Conversations**: Uses OpenAI GPT models for intelligent responses
- **Instruction-Based Behavior**: Agent behavior controlled via `instruction.txt` file
- **Environment-based Configuration**: Easy configuration via `.env` file
- **Latest LiveKit SDK**: Built with the latest LiveKit agents framework (v1.5.8+)

## Prerequisites

- Python 3.9 or higher
- LiveKit server (local or cloud)
- API keys for your chosen STT provider:
  - Deepgram API key (if using Deepgram)
  - Speechmatics API key (if using Speechmatics)
- OpenAI API key (for TTS)

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

# Speechmatics configuration (if using Speechmatics)
SPEECHMATICS_API_KEY=your_speechmatics_api_key

# OpenAI for TTS
OPENAI_API_KEY=your_openai_api_key
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
5. Processes the transcription with OpenAI GPT model based on the instructions
6. Responds using OpenAI TTS
7. Continues the conversation naturally

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

- **Interruption Handling**: Allows natural interruptions with smart thresholds
- **VAD (Voice Activity Detection)**: Silero VAD with 0.6s minimum silence duration
- **Endpointing**: Configurable delays (0.5s min, 4.0s max) for natural conversation flow
- **Interruption Thresholds**: 0.8s duration minimum, at least 1 word required

### STT Providers

**Deepgram**:
- Fast and accurate
- Supports multiple languages
- Real-time streaming
- Models: `nova-2`, `nova-3`, `nova-2-general`, etc.

**Speechmatics**:
- High accuracy
- Advanced language support
- Custom vocabulary support
- Operating points: `enhanced` (recommended) or `standard`

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

## License

MIT
