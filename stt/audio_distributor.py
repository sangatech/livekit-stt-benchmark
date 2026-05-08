from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from .base_provider import AudioFrameEnvelope


class AudioDistributor:
    """Single-consumer audio fanout for mirrored STT provider streams."""

    def __init__(self, provider_names: list[str], *, max_queue_size: int = 64) -> None:
        self._queues = {
            provider: asyncio.Queue[AudioFrameEnvelope | None](maxsize=max_queue_size)
            for provider in provider_names
        }
        self.dropped_frames: dict[str, int] = {provider: 0 for provider in provider_names}

    async def publish(self, envelope: AudioFrameEnvelope) -> None:
        for provider, queue in self._queues.items():
            try:
                queue.put_nowait(envelope)
            except asyncio.QueueFull:
                self.dropped_frames[provider] += 1
                await queue.put(envelope)

    async def close(self) -> None:
        for queue in self._queues.values():
            await queue.put(None)

    async def stream_for(self, provider: str) -> AsyncIterator[AudioFrameEnvelope]:
        queue = self._queues[provider]
        while True:
            envelope = await queue.get()
            if envelope is None:
                return
            yield envelope
