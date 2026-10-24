"""Event subsystem: AgentEvent model, durable bus, detector loop.

`start_events()` is wired into the app lifespan by the API workstream.
"""

from __future__ import annotations

import asyncio
import logging

from app.events.bus import EventBus, get_event_bus
from app.events.detectors import DetectorEngine, detector_loop, get_detector_engine
from app.events.model import EVENT_TYPES, make_event

log = logging.getLogger(__name__)

__all__ = [
    "EventBus",
    "get_event_bus",
    "DetectorEngine",
    "get_detector_engine",
    "detector_loop",
    "EVENT_TYPES",
    "make_event",
    "start_events",
    "stop_events",
]


async def start_events() -> list[asyncio.Task]:
    tasks = [asyncio.create_task(detector_loop(), name="detector_loop")]
    log.info("event detectors started")
    return tasks


async def stop_events(tasks: list[asyncio.Task]) -> None:
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    log.info("event detectors stopped")
