# Backend/application/exit_monitor.py

import asyncio
import logging
from typing import Any

from Backend.application.candle_validation import is_market_open

logger = logging.getLogger(__name__)


class ExitMonitor:
    """
    Background task that continuously monitors all open
    positions and evaluates exit conditions.

    Exit checks:
    - Stop Loss
    - Target
    - Trailing Stop
    - Time Exit
    - Market Close Exit
    """

    def __init__(
        self,
        position_store: Any,
        trade_exit_engine: Any,
        interval: float = 1.0,
    ):
        self.position_store = position_store
        self.trade_exit_engine = trade_exit_engine
        self.interval = interval
        self._running = False

    async def run(self):
        logger.info("Exit Monitor started")
        self._running = True

        while self._running:

            try:

                # Only monitor during live market
                if not is_market_open():
                    await asyncio.sleep(30)
                    continue

                positions = self.position_store.get_open_positions()

                if not positions:
                    await asyncio.sleep(self.interval)
                    continue

                for position in positions:

                    try:

                        decision = await self.trade_exit_engine.evaluate(position)

                        if decision is not None and getattr(decision, "exit_required", False):

                            logger.info(
                                "Exit triggered | %s | %s",
                                getattr(position, "symbol", None)
                                or position.get("symbol"),
                                decision.reason,
                            )

                            await self.trade_exit_engine.execute_exit(
                                position,
                                decision,
                            )

                    except Exception:
                        logger.exception(
                            "Exit evaluation failed for %s",
                            getattr(position, "symbol", None)
                            or position.get("symbol", "UNKNOWN"),
                        )

                await asyncio.sleep(self.interval)

            except asyncio.CancelledError:
                logger.info("Exit Monitor cancelled")
                break

            except Exception:
                logger.exception("Exit Monitor crashed")
                await asyncio.sleep(5)

        logger.info("Exit Monitor stopped")

    def stop(self):
        self._running = False