# Implementation Notes

## Overview
This agent is based on the IT_Curves_Bot session configuration and architecture, adapted for a simpler use case.

## Key Features Implemented

### 1. Multi-STT Support
- **Deepgram**: Configured with `nova-2` model, smart formatting, English language
- **Speechmatics**: Configured with enhanced operating point, 1.5s max delay
- Provider selection via `STT_PROVIDER` environment variable
- IT_Curves domain keyterms are loaded from `stt/keyterms.json`
  - Deepgram receives capped terms through `keyterms`
  - Speechmatics receives capped terms through `additional_vocab`

### 2. Session Configuration (from IT_Curves_Bot)
The agent uses fixed voice-session parameters based on IT_Curves_Bot:

```python
turn_handling = {
    "turn_detection": EnglishModel(),
    "endpointing": {"min_delay": 0.5, "max_delay": 4.0},
    "interruption": {
        "enabled": True,
        "discard_audio_if_uninterruptible": False,
        "min_duration": 0.8,
        "min_words": 1,
        "false_interruption_timeout": 1.5,
        "resume_false_interruption": True,
    },
    "preemptive_generation": {"enabled": True},
}

AgentSession(
    stt=stt,
    tts=tts,
    llm=llm_instance,
    vad=vad,
    turn_handling=turn_handling,
)
```

### 3. VAD Configuration
- **Silero VAD** with `min_silence_duration=0.6` (same as IT_Curves_Bot)
- Optimized for natural conversation flow

### 4. Noise Cancellation
- **BVC telephony noise cancellation** is enabled directly in `agent.py`
- Implemented the same way as IT_Curves_Bot, with `noise_cancellation.BVCTelephony()` passed to `RoomInputOptions`

### 5. Instruction-Based Behavior
- Agent behavior controlled by `instruction.txt` file
- No hardcoded prompts in code
- Easy to customize without code changes

### 6. Environment-Based Configuration
Credentials, model selection, provider selection, and benchmark settings are configurable via `.env`:
- STT provider and models
- LLM model selection
- TTS model and voice selection
- LiveKit credentials

Voice-session behavior is fixed in `agent.py`, not configured via `.env`.

## Differences from IT_Curves_Bot

### Simplified
- No multi-agent orchestration
- No supervisor system
- No complex state management
- Single conversational agent

### Retained
- Session configuration parameters
- STT provider abstraction
- VAD settings
- Interruption handling
- BVC telephony noise cancellation
- Environment-based configuration

## File Structure

```
testbot/
├── agent.py              # Main agent (simplified from IT_Curves_Bot)
├── instruction.txt       # Agent behavior (replaces hardcoded prompts)
├── requirements.txt      # Dependencies (LiveKit 1.5.8+)
├── .env.example         # Configuration template
└── README.md            # Documentation
```

## Usage

1. Configure `.env` with your credentials
2. Edit `instruction.txt` to define agent behavior
3. Run: `python agent.py dev`

The agent will use the same session settings as IT_Curves_Bot for optimal voice quality and natural conversation flow.
