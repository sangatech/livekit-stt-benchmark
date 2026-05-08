from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

from stt.audio_distributor import AudioDistributor
from stt.base_provider import AudioFrameEnvelope
from stt.provider_manager import ProviderSelection

from .engine import BenchmarkEngine

logger = logging.getLogger(__name__)


class LiveKitShadowBenchmark:
    """Runs mirrored STT streams from a single LiveKit audio frame iterator."""

    def __init__(self, *, selection: ProviderSelection, engine: BenchmarkEngine) -> None:
        self.selection = selection
        self.engine = engine
        self._tasks: list[asyncio.Task[None]] = []

    async def run(self, *, call_id: str, room_id: str, audio_frames: AsyncIterator[Any]) -> None:
        providers = self.selection.active_providers
        distributor = AudioDistributor([provider.provider_name for provider in providers])
        await self.engine.start_call(call_id=call_id, room_id=room_id)

        for provider in providers:
            self._tasks.append(
                asyncio.create_task(
                    self._consume_provider(provider=provider, distributor=distributor),
                    name=f"stt-benchmark-{provider.provider_name}",
                )
            )

        sequence_id = 0
        try:
            async for frame in audio_frames:
                await distributor.publish(AudioFrameEnvelope(sequence_id=sequence_id, frame=frame))
                sequence_id += 1
        finally:
            await distributor.close()
            for task in self._tasks:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            await self.engine.end_call(call_id)

    async def _consume_provider(self, *, provider, distributor: AudioDistributor) -> None:
        try:
            async for event in provider.stream(distributor.stream_for(provider.provider_name)):
                await self.engine.observe_transcript(event)
        except Exception:
            logger.exception("STT benchmark provider failed: %s", provider.provider_name)
