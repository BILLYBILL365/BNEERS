import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis as AsyncRedis

from app.config import get_settings
from app.database import get_session_factory
from app.redis_bus import RedisBus
from app.routers import tasks, decisions, agents, websocket
from app.routers.agents import _agent_statuses
from app.routers.decisions import set_bus
from app.services.audit import AuditService
from app.runner import AgentRunner
from app.services.discord_notifier import DiscordNotifier


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    if settings.TESTING:
        yield  # Skip all setup in test mode
        return

    # Connect to Redis
    redis_client = AsyncRedis.from_url(settings.REDIS_URL)
    bus = RedisBus(redis_client=redis_client)

    # Wire bus into decisions router (for publishing approved/rejected events)
    set_bus(bus)

    # Start King Solomon Discord bot (no-op if DISCORD_BOT_TOKEN is empty)
    notifier = DiscordNotifier(
        bot_token=settings.DISCORD_BOT_TOKEN,
        approvals_channel_id=settings.DISCORD_APPROVALS_CHANNEL_ID,
        updates_channel_id=settings.DISCORD_UPDATES_CHANNEL_ID,
        alerts_channel_id=settings.DISCORD_ALERTS_CHANNEL_ID,
        backend_base_url=settings.DISCORD_BACKEND_URL,
    )
    try:
        await asyncio.wait_for(notifier.start(), timeout=10.0)
    except asyncio.TimeoutError:
        pass  # Bot failed to connect; handle_event will be a no-op until _client is ready

    # Subscribe notifier to bus events
    for event_type in (
        "decision.pending",
        "decision.approved",
        "decision.rejected",
        "task.created",
        "task.completed",
        "agent.status",
        "agent.alert",
        "spend.exceeded",
    ):
        await bus.subscribe(event_type, notifier.handle_event)

    # Pass session factory to AuditService — each log() call opens its own session
    session_factory = get_session_factory()
    audit = AuditService(session_factory=session_factory)

    # Start all C-Suite agents
    runner = AgentRunner(
        bus=bus,
        audit=audit,
        anthropic_api_key=settings.ANTHROPIC_API_KEY,
        weekly_soft_cap=settings.WEEKLY_SOFT_CAP_TOTAL,
        daily_cap_ads=settings.DAILY_HARD_CAP_ADS,
        daily_cap_apis=settings.DAILY_HARD_CAP_APIS,
        model_smart=settings.LLM_MODEL_SMART,
        model_fast=settings.LLM_MODEL_FAST,
    )
    runner.status_store = _agent_statuses
    await runner.start()

    # Run bus event loop as background task
    bus_task = asyncio.create_task(bus.run_forever())

    yield  # App is running

    # Shutdown
    bus_task.cancel()
    try:
        await bus_task
    except asyncio.CancelledError:
        pass
    await runner.stop()
    await notifier.stop()

    await redis_client.aclose()


app = FastAPI(title="Project Million", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router)
app.include_router(decisions.router)
app.include_router(agents.router)
app.include_router(websocket.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
