# CLAUDE.md — Project Million (BNEERS)

## What This Is

An autonomous multi-agent system ("Project Million") that runs AI agents organized as a virtual company. C-Suite agents (CSO, CTO, CMO, CFO, COO) coordinate worker agents to identify SaaS opportunities, build products, and grow revenue. A human "Board" approves major decisions via Mission Control dashboard or Discord.

## Repository Structure

```
├── backend/           # FastAPI + Python 3.12
│   ├── app/
│   │   ├── agents/    # C-Suite agents (cso, cto, cmo, cfo, coo) + workers/
│   │   ├── models/    # SQLAlchemy models (task, decision, audit_log)
│   │   ├── routers/   # API endpoints (tasks, decisions, agents, cycles, websocket)
│   │   ├── schemas/   # Pydantic schemas (decision, task, events)
│   │   ├── services/  # Business logic (audit, bus, decisions, llm, spend_tracker, discord_notifier, watchdog)
│   │   ├── config.py  # pydantic-settings config from env vars
│   │   ├── database.py # Async SQLAlchemy engine + session factory
│   │   ├── main.py    # FastAPI app with lifespan (Redis, agents, scheduler, Discord)
│   │   ├── redis_bus.py # Redis-backed pub/sub event bus (FIFO via lpush)
│   │   ├── runner.py  # AgentRunner — starts/stops all agents, heartbeat loop
│   │   └── scheduler.py # AgentScheduler — fires business cycles on interval
│   ├── alembic/       # DB migrations (PostgreSQL)
│   ├── tests/         # pytest test suite
│   ├── Dockerfile
│   ├── pyproject.toml # hatchling build, dependencies
│   └── railway.json   # Railway deployment config
├── frontend/          # Next.js 16 + React 19 + Tailwind CSS 4
│   ├── app/           # App router (single page: Mission Control dashboard)
│   ├── components/    # TopBar, KPICards, ApprovalQueue, AgentStatusGrid, TaskFeed
│   ├── hooks/         # useWebSocket (real-time event updates)
│   ├── lib/           # api.ts (REST client)
│   ├── types/         # TypeScript types
│   ├── Dockerfile
│   ├── railway.json
│   └── AGENTS.md      # Next.js version warning — read node_modules/next/dist/docs/ before writing code
├── docs/              # Design specs (superpowers/)
├── scripts/           # simulate_agents.py, staging_smoke_test.py
├── docker-compose.yml # Local dev: postgres, redis, backend, frontend
├── DESIGN.md          # Full architecture & design document
└── .env.example       # All required environment variables
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy (async), Alembic, Pydantic v2 |
| Database | PostgreSQL 16 (asyncpg driver) |
| Message Bus | Redis 7 (async, FIFO via lpush) |
| AI | Anthropic Claude API (claude-sonnet-4-6 smart, claude-haiku-4-5 fast) |
| Notifications | Discord bot ("King Solomon") |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4 |
| Deployment | Railway (Docker), docker-compose for local dev |

## Development Setup

### Local with Docker Compose
```bash
cp .env.example .env
# Edit .env with your values (ANTHROPIC_API_KEY, DISCORD_BOT_TOKEN optional)
docker compose up
```
- Backend: http://localhost:8000 (auto-runs `alembic upgrade head`)
- Frontend: http://localhost:3000
- PostgreSQL: localhost:5432
- Redis: localhost:6379

### Backend Only
```bash
cd backend
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Frontend Only
```bash
cd frontend
npm ci
npm run dev
```

## Running Tests

```bash
cd backend
pytest                    # all tests
pytest tests/test_foo.py  # single file
pytest -x                 # stop on first failure
```

- Tests use `TESTING=true` env var (set in `conftest.py`) which skips lifespan startup
- Uses `fakeredis` for Redis, `aiosqlite` for DB in tests
- pytest-asyncio with `asyncio_mode = "auto"` — all async tests run automatically
- Test files: `backend/tests/` (30+ test files covering agents, services, routers, integration)

## Key Architectural Patterns

### Agent System
- All agents extend `BaseAgent` (`app/agents/base.py`) which provides: lifecycle (start/stop), pub/sub via Redis bus, decision requests, retry-with-backoff, heartbeat, escalation
- C-Suite agents: CSO, CTO, CMO, CFO, COO — each in `app/agents/{name}.py`
- Worker agents in `app/agents/workers/` (market_scanner, code_writer, content_writer, etc.)
- `AgentRunner` manages all agent lifecycles and heartbeats
- `AgentScheduler` fires periodic business cycles (`cycle.start` event) every `CYCLE_INTERVAL_SECONDS` (default 6h)

### Event Bus
- Redis-backed pub/sub via `RedisBus` (`app/redis_bus.py`)
- Events are `BusEvent` (type + payload dict) defined in `app/schemas/events.py`
- Key event types: `cycle.start`, `cycle.completed`, `decision.pending`, `decision.approved`, `decision.rejected`, `task.created`, `task.completed`, `agent.status`, `agent.alert`, `leads.approved`, `spend.exceeded`

### Decision Flow
- Agents call `self.request_decision()` to post decisions for Board approval
- Decisions go through: pending → approved/rejected
- Board approves via REST API or Discord bot
- `cycle_id` threads decisions to their originating cycle

### Frontend
- Single-page Mission Control dashboard (Next.js App Router)
- Real-time updates via WebSocket (`/ws` endpoint)
- REST API client in `lib/api.ts`
- Components: TopBar, KPICards, ApprovalQueue, AgentStatusGrid, TaskFeed

## Important Conventions

- **Next.js 16**: The frontend uses Next.js 16 which has breaking changes from earlier versions. Always check `node_modules/next/dist/docs/` before writing frontend code.
- **Async everywhere**: Backend is fully async (asyncpg, async Redis, async SQLAlchemy). Never use sync DB/Redis calls.
- **Event-driven**: Agents communicate via the Redis event bus, not direct calls. Follow the pub/sub pattern.
- **Config via env**: All config flows through `app/config.py` (pydantic-settings). Add new settings there.
- **Alembic migrations**: Database schema changes require Alembic migrations in `backend/alembic/versions/`.
- **Spending caps**: The system has configurable spending limits (daily, weekly, monthly) enforced by `SpendTracker`.
- **No linter/formatter configured**: No ESLint, Black, Ruff, or Prettier configs exist. Match existing code style.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/tasks` | List tasks |
| GET | `/decisions?status=` | List decisions (filter by status) |
| POST | `/decisions/{id}/approve` | Approve a decision |
| POST | `/decisions/{id}/reject` | Reject a decision |
| GET | `/agents/status` | Agent status list |
| POST | `/cycles/trigger` | Manually trigger a business cycle |
| WS | `/ws` | WebSocket for real-time events |

## Environment Variables

See `.env.example` for the full list. Key variables:
- `DATABASE_URL` — PostgreSQL connection string
- `REDIS_URL` — Redis connection string
- `ANTHROPIC_API_KEY` — Leave empty for mock/no-llm mode
- `CYCLE_INTERVAL_SECONDS` — Business cycle interval (default 21600 = 6h)
- `DISCORD_BOT_TOKEN` — Leave empty to disable Discord notifications
- Spending caps: `DAILY_HARD_CAP_ADS`, `DAILY_HARD_CAP_APIS`, `WEEKLY_SOFT_CAP_TOTAL`, `MONTHLY_HARD_CEILING`
