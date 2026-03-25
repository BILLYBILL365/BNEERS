import asyncio
from collections import defaultdict
from collections.abc import Callable, Awaitable
from redis.asyncio import Redis
from app.schemas.events import BusEvent

EventHandler = Callable[[BusEvent], Awaitable[None] | None]


class RedisBus:
    CHANNEL = "project_million_bus"

    def __init__(self, redis_client: Redis):
        self._redis = redis_client
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    async def publish(self, event: BusEvent) -> None:
        await self._redis.lpush(self.CHANNEL, event.model_dump_json())

    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    async def process_one(self) -> bool:
        """Process one message from the queue. Returns True if a message was processed."""
        raw = await self._redis.rpop(self.CHANNEL)
        if raw is None:
            return False
        event = BusEvent.model_validate_json(raw)
        for handler in self._handlers.get(event.type, []):
            coro = handler(event)
            if asyncio.iscoroutine(coro):
                await coro
        return True

    async def run_forever(self) -> None:
        """Continuously process messages. Run as a background task."""
        while True:
            processed = await self.process_one()
            if not processed:
                await asyncio.sleep(0.05)


def get_bus(redis_client: Redis) -> RedisBus:
    return RedisBus(redis_client=redis_client)
