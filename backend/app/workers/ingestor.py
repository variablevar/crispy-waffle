"""Ingestor: starts/stops the Binance + Bybit websocket workers for the
tracked symbols and keeps LiveState hot."""

from __future__ import annotations

import asyncio
import logging

from app.services import binance_ws, bybit_ws

log = logging.getLogger(__name__)


class Ingestor:
    def __init__(self) -> None:
        self._tasks: list[asyncio.Task] = []
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self, symbols: list[str]) -> None:
        if self._running or not symbols:
            return
        self._running = True
        self._tasks = [
            asyncio.create_task(binance_ws.run(symbols), name="binance_ws"),
            asyncio.create_task(bybit_ws.run(symbols), name="bybit_ws"),
        ]
        log.info("ingestor started for %d symbols", len(symbols))

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        log.info("ingestor stopped")


_ingestor = Ingestor()


def get_ingestor() -> Ingestor:
    return _ingestor
