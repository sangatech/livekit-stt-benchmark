import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
    llm,
    AgentSession,
)
from livekit.agents.voice import Agent
from livekit.plugins import deepgram, speechmatics, openai, silero

load_dotenv()


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
    provider = os.getenv("STT_PROVIDER", "deepgram").lower()
    
    if provider == "deepgram":
        model = os.getenv("DEEPGRAM_STT_MODEL", "nova-2")
        return deepgram.STT(
            model=model,
            language="en",
            interim_results=False,
            smart_format=True,
        )
    
    elif provider == "speechmatics":
        from livekit.plugins.speechmatics import OperatingPoint
        operating_point_str = os.getenv("SPEECHMATICS_OPERATING_POINT", "enhanced")
        operating_point = OperatingPoint.ENHANCED if operating_point_str == "enhanced" else OperatingPoint.STANDARD
        
        return speechmatics.STT(
            operating_point=operating_point,
            language="en",
            max_delay=1.5,
            enable_diarization=False,
        )
    
    else:
        raise ValueError(f"Unknown STT provider: {provider}. Use 'deepgram' or 'speechmatics'")


async def entrypoint(ctx: JobContext):
    """Main entry point for the voice agent."""
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    
    # Load instructions from file
    instructions = load_instructions()
    
    # Get STT provider from environment
    stt = get_stt_provider()
    
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
        min_silence_duration=0.6,
    )
    
    # Create agent with instructions from file
    agent = Agent(
        instructions=instructions,
        llm=llm_instance,
    )
    
    # Create session with proper configuration
    session = AgentSession(
        stt=stt,
        tts=tts,
        vad=vad,
        allow_interruptions=True,
        min_interruption_duration=0.8,
        min_interruption_words=1,
        min_endpointing_delay=0.5,
        max_endpointing_delay=4.0,
    )
    
    # Start the session with the agent
    await session.start(agent=agent, room=ctx.room)
    
    # Give a brief delay then greet
    await asyncio.sleep(0.5)
    await session.say("Hello! How can I help you today?", allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
        ),
    )
