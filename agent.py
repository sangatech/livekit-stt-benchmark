import asyncio
import os
import time
from pathlib import Path
from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    RoomInputOptions,
    WorkerOptions,
    cli,
    llm,
    AgentSession,
)
from livekit.agents.voice import Agent
from benchmark.client import BenchmarkHttpPublisher
from livekit.plugins import noise_cancellation, openai, silero
from livekit.plugins.turn_detector.english import EnglishModel
from benchmark.settings import setting
from stt.benchmarking_stt import BenchmarkingSTT
from stt.provider_manager import BenchmarkMode, STTProviderManager

load_dotenv()

VAD_MIN_SILENCE_DURATION = 0.6
MIN_ENDPOINTING_DELAY = 0.5
MAX_ENDPOINTING_DELAY = 4.0
ALLOW_INTERRUPTION = True
DISCARD_AUDIO_IF_UNINTERRUPTIBLE = False
MIN_INTERRUPTION_DURATION = 0.8
MIN_INTERRUPTION_WORDS = 1
FALSE_INTERRUPTION_TIMEOUT = 1.5
RESUME_FALSE_INTERRUPTION = True
PREEMPTIVE_GENERATION = True


def load_instructions():
    """Load agent instructions from instruction.txt file."""
    instruction_file = Path(__file__).parent / "instruction.txt"
    try:
        with open(instruction_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        raise FileNotFoundError(
            f"instruction.txt not found at {instruction_file}. "
            "Please create this file with your agent's instructions."
        )


def get_stt_provider():
    """Get configured STT provider from environment."""
    selection = STTProviderManager().select()
    if selection.mode != BenchmarkMode.PRODUCTION:
        secondary = selection.secondary.provider_name if selection.secondary else "none"
        print(
            "STT benchmarking enabled: "
            f"mode={selection.mode.value} primary={selection.primary.provider_name} secondary={secondary}"
        )
    return selection.primary.livekit_stt()


def get_turn_handling():
    """Mirror IT_Curves-style English turn detection with current LiveKit APIs."""
    turn_handling = {
        "endpointing": {
            "min_delay": MIN_ENDPOINTING_DELAY,
            "max_delay": MAX_ENDPOINTING_DELAY,
        },
        "interruption": {
            "enabled": ALLOW_INTERRUPTION,
            "discard_audio_if_uninterruptible": DISCARD_AUDIO_IF_UNINTERRUPTIBLE,
            "min_duration": MIN_INTERRUPTION_DURATION,
            "min_words": MIN_INTERRUPTION_WORDS,
            "false_interruption_timeout": FALSE_INTERRUPTION_TIMEOUT,
            "resume_false_interruption": RESUME_FALSE_INTERRUPTION,
        },
        "preemptive_generation": {
            "enabled": PREEMPTIVE_GENERATION,
        },
    }

    try:
        turn_handling["turn_detection"] = EnglishModel()
    except RuntimeError as exc:
        print(
            "Failed to initialize LiveKit EnglishModel turn detection; "
            f"continuing without model-based turn detection: {exc}"
        )

    return turn_handling


async def entrypoint(ctx: JobContext):
    """Main entry point for the voice agent."""
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    
    # Load instructions from file
    instructions = load_instructions()
    
    provider_manager = STTProviderManager(
        call_id=_call_id_from_context(ctx),
        room_id=_room_id_from_context(ctx),
    )
    provider_selection = provider_manager.select()
    if provider_selection.mode != BenchmarkMode.PRODUCTION:
        secondary = provider_selection.secondary.provider_name if provider_selection.secondary else "none"
        print(
            "STT benchmarking enabled: "
            f"mode={provider_selection.mode.value} "
            f"primary={provider_selection.primary.provider_name} secondary={secondary}"
        )
    primary_stt = provider_selection.primary.livekit_stt()
    if provider_selection.mode != BenchmarkMode.PRODUCTION and provider_selection.secondary is not None:
        stt = BenchmarkingSTT(
            primary_stt=primary_stt,
            primary_provider=provider_selection.primary.provider_name,
            shadow_stt=provider_selection.secondary.livekit_stt(),
            shadow_provider=provider_selection.secondary.provider_name,
            call_id=provider_manager.call_id or _call_id_from_context(ctx),
            room_id=provider_manager.room_id or _room_id_from_context(ctx),
        )
    else:
        stt = primary_stt

    bvc_options = noise_cancellation.BVCTelephony()
    
    # Get TTS model from environment
    tts_model = os.getenv("OPENAI_TTS_MODEL", "tts-1")
    tts_voice = os.getenv("OPENAI_TTS_VOICE", "alloy")
    tts = openai.TTS(
        model=tts_model,
        voice=tts_voice,
    )
    
    # Get LLM model from environment
    llm_model = os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini")
    llm_instance = openai.LLM(
        model=llm_model,
    )
    
    # Load VAD with configuration
    vad = silero.VAD.load(
        min_silence_duration=VAD_MIN_SILENCE_DURATION,
    )
    
    # Create agent with instructions from file
    agent = Agent(
        instructions=instructions,
    )
    
    # Create session with proper configuration
    session = AgentSession(
        stt=stt,
        llm=llm_instance,
        tts=tts,
        vad=vad,
        turn_handling=get_turn_handling(),
    )

    if provider_selection.mode == BenchmarkMode.PRODUCTION:
        _attach_benchmark_publisher(
            session=session,
            call_id=provider_manager.call_id or _call_id_from_context(ctx),
            room_id=provider_manager.room_id or _room_id_from_context(ctx),
            provider=provider_selection.primary.provider_name,
        )
    
    # Start the session with the agent
    await session.start(
        agent=agent,
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=bvc_options,
        ),
    )
    
    # Give a brief delay then greet
    await asyncio.sleep(0.5)
    await session.say("Hello! How can I help you today?", allow_interruptions=True)


def _room_id_from_context(ctx: JobContext) -> str:
    room = getattr(ctx, "room", None)
    return str(getattr(room, "name", None) or getattr(room, "sid", None) or "unknown-room")


def _call_id_from_context(ctx: JobContext) -> str:
    configured = os.getenv("BENCHMARK_CALL_ID")
    if configured:
        return configured
    room_id = _room_id_from_context(ctx)
    return f"{room_id}-{int(time.time())}"


def _attach_benchmark_publisher(*, session: AgentSession, call_id: str, room_id: str, provider: str) -> None:
    if not bool(setting("benchmark_publish_events", os.getenv("BENCHMARK_PUBLISH_EVENTS", "true").lower() == "true")):
        return

    publisher = BenchmarkHttpPublisher()
    sequence = 0

    @session.on("user_input_transcribed")
    def on_user_input_transcribed(event):
        nonlocal sequence
        transcript = getattr(event, "transcript", "")
        if not transcript:
            return
        payload = {
            "provider": provider,
            "transcript": transcript,
            "is_final": bool(getattr(event, "is_final", False)),
            "confidence": None,
            "timestamp": float(getattr(event, "created_at", time.time())),
            "latency_ms": None,
            "sequence_id": sequence,
            "call_id": call_id,
            "room_id": room_id,
            "raw": {
                "speaker_id": getattr(event, "speaker_id", None),
                "language": str(getattr(event, "language", "") or ""),
                "source": "livekit_agent_session",
            },
        }
        sequence += 1
        asyncio.create_task(_safe_publish_transcript(publisher, payload))


async def _safe_publish_transcript(publisher: BenchmarkHttpPublisher, payload: dict) -> None:
    try:
        await publisher.publish_transcript(payload)
    except Exception as exc:
        print(f"failed to publish benchmark transcript: {exc}")


if __name__ == "__main__":
    cli.run_app(
        
        WorkerOptions(
            port=int(os.environ.get("LIVEKIT_PORT", 7880)),
            entrypoint_fnc=entrypoint,
            num_idle_processes=3,
            load_threshold=0.65,
            ws_url=os.environ.get("LIVEKIT_URL"),
            api_key=os.environ.get("LIVEKIT_API_KEY"),
            api_secret=os.environ.get("LIVEKIT_API_SECRET"),
        )
    )
