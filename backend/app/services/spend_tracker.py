from __future__ import annotations

from collections import defaultdict
from typing import Literal

from app.redis_bus import RedisBus
from app.schemas.events import BusEvent

SpendCategory = Literal["ads", "apis"]


class SpendTracker:
    """Tracks API and ad spend per category. Publishes spend.exceeded on cap breach.

    Totals reset daily via reset_daily() (called by CFO on midnight timer in Phase 4).
    """

    def __init__(
        self,
        bus: RedisBus,
        daily_cap_ads: float,
        daily_cap_apis: float,
    ) -> None:
        self._bus = bus
        self._caps: dict[str, float] = {
            "ads": daily_cap_ads,
            "apis": daily_cap_apis,
        }
        self._daily: dict[str, float] = defaultdict(float)

    def daily_total(self, category: str) -> float:
        return self._daily[category]

    async def record(self, category: str, amount: float) -> bool:
        """Record spend. Returns True if daily cap was exceeded."""
        self._daily[category] += amount
        cap = self._caps.get(category, float("inf"))
        if self._daily[category] > cap:
            await self._bus.publish(
                BusEvent(
                    type="spend.exceeded",
                    payload={
                        "category": category,
                        "amount": amount,
                        "daily_total": self._daily[category],
                        "cap": cap,
                    },
                )
            )
            return True
        return False

    def reset_daily(self) -> None:
        self._daily.clear()
