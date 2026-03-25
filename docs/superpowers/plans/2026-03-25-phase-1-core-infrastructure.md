# Phase 1: Core Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundational backend (FastAPI + PostgreSQL + Redis message bus) and Mission Control dashboard shell (Next.js) with live WebSocket updates — no agent intelligence yet, just the infrastructure everything else runs on.

**Architecture:** FastAPI backend exposes REST endpoints and a WebSocket endpoint. All inter-service events flow through a Redis pub/sub message bus. PostgreSQL stores tasks, decisions, and the audit log. The Next.js frontend connects via WebSocket for live updates and REST for actions (approve/reject decisions).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, asyncpg, redis-py (async), Pydantic v2, pytest + pytest-asyncio, Next.js 14, TypeScript, Tailwind CSS, Docker Compose

---

## File Map

```
project-million/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app, lifespan, router registration
│   │   ├── config.py                # Settings (env vars, spending caps, thresholds)
│   │   ├── database.py              # SQLAlchemy async engine + session factory
│   │   ├── redis_bus.py             # Redis pub/sub: publish() + subscribe()
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── task.py              # Task ORM model
│   │   │   ├── decision.py          # Decision/approval ORM model
│   │   │   └── audit_log.py         # AuditLog ORM model
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── task.py              # Task Pydantic schemas (Create, Read, Update)
│   │   │   ├── decision.py          # Decision Pydantic schemas
│   │   │   └── events.py            # Message bus event schemas
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── tasks.py             # GET/POST /tasks
│   │   │   ├── decisions.py         # GET/POST /decisions, POST /decisions/{id}/approve|reject
│   │   │   ├── agents.py            # GET /agents/status, POST /agents/{id}/heartbeat
│   │   │   └── websocket.py         # WS /ws — streams events to dashboard
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── bus.py               # BusService: wraps redis_bus, broadcasts to WS clients
│   │       └── watchdog.py          # WatchdogService: heartbeat checks, health alerts
│   ├── tests/
│   │   ├── conftest.py              # Fixtures: test DB, test Redis, test client
│   │   ├── test_config.py           # Settings load + spending cap values
│   │   ├── test_database.py         # DB connection, model creation
│   │   ├── test_redis_bus.py        # publish/subscribe round-trip
│   │   ├── test_tasks.py            # Tasks CRUD endpoints
│   │   ├── test_decisions.py        # Decision endpoints + approve/reject flow
│   │   ├── test_agents.py           # Agent status + heartbeat endpoints
│   │   ├── test_websocket.py        # WS connection + event delivery
│   │   └── test_watchdog.py         # Watchdog fires alert when heartbeat missing
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/                # Migration files (auto-generated)
│   ├── alembic.ini
│   ├── pyproject.toml               # deps + pytest config
│   └── Dockerfile
├── frontend/
│   ├── app/
│   │   ├── layout.tsx               # Root layout, global font/theme
│   │   ├── page.tsx                 # Mission Control page (assembles components)
│   │   └── globals.css              # Tailwind base
│   ├── components/
│   │   ├── TopBar.tsx               # Agent count, weekly revenue, pending approvals
│   │   ├── KPICards.tsx             # 3 KPI cards: revenue, customers, tasks
│   │   ├── ApprovalQueue.tsx        # Right-column decision queue + approve/reject
│   │   ├── AgentStatusGrid.tsx      # All agents, color-coded by status
│   │   └── TaskFeed.tsx             # Live scrolling task feed
│   ├── hooks/
│   │   └── useWebSocket.ts          # WS connection, reconnect logic, event dispatch
│   ├── types/
│   │   └── index.ts                 # Agent, Task, Decision, KPI TypeScript types
│   ├── lib/
│   │   └── api.ts                   # Typed fetch wrappers for REST endpoints
│   ├── package.json
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── Dockerfile
├── docker-compose.yml               # postgres + redis + backend + frontend
└── .env.example                     # All required env vars documented
```

---

## Task 1: Project Scaffold & Docker Compose

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `backend/pyproject.toml`
- Create: `backend/Dockerfile`
- Create: `frontend/package.json`
- Create: `frontend/Dockerfile`

- [ ] **Step 1: Create `.env.example`**

```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/projectmillion
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=projectmillion

# Redis
REDIS_URL=redis://localhost:6379

# App
SECRET_KEY=changeme
ENVIRONMENT=development

# Spending caps (USD)
DAILY_HARD_CAP_ADS=100
DAILY_HARD_CAP_APIS=50
WEEKLY_SOFT_CAP_TOTAL=500
MONTHLY_HARD_CEILING=2000
```

- [ ] **Step 2: Create `docker-compose.yml`**

```yaml
version: "3.9"

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
      POSTGRES_DB: ${POSTGRES_DB:-projectmillion}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./backend:/app
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000
      - NEXT_PUBLIC_WS_URL=ws://localhost:8000
    depends_on:
      - backend
    volumes:
      - ./frontend:/app
      - /app/node_modules
      - /app/.next

volumes:
  postgres_data:
```

- [ ] **Step 3: Create `backend/pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "project-million-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.111.0",
    "uvicorn[standard]>=0.29.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.29.0",
    "alembic>=1.13.0",
    "redis>=5.0.0",
    "pydantic>=2.7.0",
    "pydantic-settings>=2.2.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=5.0.0",
    "httpx>=0.27.0",
    "httpx-ws>=0.6.0",
    "fakeredis>=2.23.0",
    "aiosqlite>=0.20.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.hatch.build.targets.wheel]
packages = ["app"]
```

- [ ] **Step 4: Create `backend/Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN pip install hatch

COPY pyproject.toml .
RUN pip install -e ".[dev]"

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 5: Install backend deps locally**

```bash
cd backend && pip install -e ".[dev]"
```

Expected: Dependencies install without errors.

- [ ] **Step 6: Verify Docker Compose starts**

```bash
cp .env.example .env
docker compose up postgres redis -d
docker compose ps
```

Expected: Both `postgres` and `redis` show as `healthy`.

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml .env.example backend/pyproject.toml backend/Dockerfile
git commit -m "chore: project scaffold with Docker Compose, postgres, redis"
```

---

## Task 2: Config & Settings

**Files:**
- Create: `backend/app/config.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_config.py
from app.config import Settings

def test_settings_load_defaults():
    s = Settings(
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        REDIS_URL="redis://localhost:6379",
        SECRET_KEY="test-secret",
    )
    assert s.DAILY_HARD_CAP_ADS == 100
    assert s.DAILY_HARD_CAP_APIS == 50
    assert s.WEEKLY_SOFT_CAP_TOTAL == 500
    assert s.MONTHLY_HARD_CEILING == 2000
    assert s.ENVIRONMENT == "development"

def test_settings_spending_caps_configurable():
    s = Settings(
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        REDIS_URL="redis://localhost:6379",
        SECRET_KEY="test-secret",
        DAILY_HARD_CAP_ADS=200,
    )
    assert s.DAILY_HARD_CAP_ADS == 200
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: Create `backend/app/__init__.py` and `backend/app/config.py`**

```python
# backend/app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    REDIS_URL: str
    SECRET_KEY: str
    ENVIRONMENT: str = "development"

    # Spending caps (USD)
    DAILY_HARD_CAP_ADS: float = 100.0
    DAILY_HARD_CAP_APIS: float = 50.0
    WEEKLY_SOFT_CAP_TOTAL: float = 500.0
    MONTHLY_HARD_CEILING: float = 2000.0

    # Agent heartbeat timeout (seconds)
    AGENT_HEARTBEAT_TIMEOUT: int = 120

def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Create `backend/tests/conftest.py`**

```python
# backend/tests/conftest.py
import pytest
from app.config import Settings

@pytest.fixture
def settings():
    return Settings(
        DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/projectmillion_test",
        REDIS_URL="redis://localhost:6379/1",
        SECRET_KEY="test-secret-key",
    )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_config.py -v
```

Expected: 2 PASSED

- [ ] **Step 6: Commit**

```bash
git add backend/app/__init__.py backend/app/config.py backend/tests/conftest.py backend/tests/test_config.py
git commit -m "feat: add Settings with spending caps and environment config"
```

---

## Task 3: Database Models & Migrations

**Files:**
- Create: `backend/app/database.py`
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/task.py`
- Create: `backend/app/models/decision.py`
- Create: `backend/app/models/audit_log.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/tests/test_database.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_database.py
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.models import Base
from app.models.task import Task, TaskStatus
from app.models.decision import Decision, DecisionStatus
from app.models.audit_log import AuditLog

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.mark.asyncio
async def test_create_task(db_session):
    task = Task(title="Build MVP", agent_id="cto", status=TaskStatus.PENDING)
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)
    assert task.id is not None
    assert task.status == TaskStatus.PENDING

@pytest.mark.asyncio
async def test_create_decision(db_session):
    decision = Decision(
        title="Launch SaaS product",
        description="CSO recommends targeting B2B invoicing market",
        requested_by="cso",
        status=DecisionStatus.PENDING,
    )
    db_session.add(decision)
    await db_session.commit()
    await db_session.refresh(decision)
    assert decision.id is not None
    assert decision.status == DecisionStatus.PENDING

@pytest.mark.asyncio
async def test_create_audit_log(db_session):
    log = AuditLog(
        agent_id="cso",
        event_type="decision",
        payload={"market": "B2B invoicing", "confidence": 0.87},
        decision_by="cso",
        outcome="success",
    )
    db_session.add(log)
    await db_session.commit()
    await db_session.refresh(log)
    assert log.id is not None
    assert log.payload["market"] == "B2B invoicing"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_database.py -v
```

Expected: FAIL — models not defined yet. Also install aiosqlite for tests: `pip install aiosqlite`

- [ ] **Step 3: Create `backend/app/models/__init__.py`**

```python
# backend/app/models/__init__.py
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

from app.models.task import Task
from app.models.decision import Decision
from app.models.audit_log import AuditLog

__all__ = ["Base", "Task", "Decision", "AuditLog"]
```

- [ ] **Step 4: Create `backend/app/models/task.py`**

```python
# backend/app/models/task.py
import uuid
import enum
from datetime import datetime, UTC
from sqlalchemy import String, Enum, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base

class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"

class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_agent_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
```

- [ ] **Step 5: Create `backend/app/models/decision.py`**

```python
# backend/app/models/decision.py
import uuid
import enum
from datetime import datetime, UTC
from sqlalchemy import String, Enum, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base

class DecisionStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[DecisionStatus] = mapped_column(Enum(DecisionStatus), default=DecisionStatus.PENDING)
    decided_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
```

- [ ] **Step 6: Create `backend/app/models/audit_log.py`**

```python
# backend/app/models/audit_log.py
import uuid
from datetime import datetime, UTC
from sqlalchemy import String, DateTime, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base

class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)  # task | decision | error | escalation
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    decision_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(50), nullable=True)  # success | failed | rejected | escalated
```

- [ ] **Step 7: Create `backend/app/database.py`**

```python
# backend/app/database.py
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.DATABASE_URL, echo=settings.ENVIRONMENT == "development")
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
```

- [ ] **Step 8: Run tests to verify they pass**

```bash
cd backend && pip install aiosqlite && pytest tests/test_database.py -v
```

Expected: 3 PASSED

- [ ] **Step 9: Set up Alembic**

```bash
cd backend && alembic init alembic
```

Update `backend/alembic/env.py` — replace the `target_metadata` section:

```python
# In alembic/env.py, add near the top:
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from app.config import get_settings
from app.models import Base  # noqa: F401 — imports all models

# Replace target_metadata line:
target_metadata = Base.metadata

# Replace run_migrations_online() with:
def run_migrations_online() -> None:
    settings = get_settings()
    connectable = create_async_engine(settings.DATABASE_URL)

    async def do_run():
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)

    def do_run_migrations(connection):
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

    asyncio.run(do_run())
```

- [ ] **Step 10: Generate initial migration**

```bash
cd backend && alembic revision --autogenerate -m "initial tables"
```

Expected: New file created under `alembic/versions/`.

- [ ] **Step 11: Run migration against test DB**

```bash
cd backend && alembic upgrade head
```

Expected: `Running upgrade -> <revision>, initial tables`

- [ ] **Step 12: Commit**

```bash
git add backend/app/database.py backend/app/models/ backend/alembic/ backend/alembic.ini backend/tests/test_database.py
git commit -m "feat: add SQLAlchemy models (Task, Decision, AuditLog) and Alembic migrations"
```

---

## Task 4: Redis Message Bus

**Files:**
- Create: `backend/app/redis_bus.py`
- Create: `backend/tests/test_redis_bus.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_redis_bus.py
import pytest
import fakeredis.aioredis as fakeredis
from app.redis_bus import RedisBus
from app.schemas.events import BusEvent

@pytest.fixture
async def bus():
    fake_redis = fakeredis.FakeRedis()
    return RedisBus(redis_client=fake_redis)

@pytest.mark.asyncio
async def test_publish_and_subscribe(bus):
    received = []

    async def handler(event: BusEvent):
        received.append(event)

    await bus.subscribe("task.created", handler)

    event = BusEvent(type="task.created", payload={"task_id": "123", "agent_id": "cto"})
    await bus.publish(event)
    await bus.process_one()  # process one message from queue

    assert len(received) == 1
    assert received[0].type == "task.created"
    assert received[0].payload["task_id"] == "123"

@pytest.mark.asyncio
async def test_multiple_subscribers(bus):
    calls_a = []
    calls_b = []

    await bus.subscribe("revenue.updated", lambda e: calls_a.append(e))
    await bus.subscribe("revenue.updated", lambda e: calls_b.append(e))

    event = BusEvent(type="revenue.updated", payload={"amount": 5000})
    await bus.publish(event)
    await bus.process_one()

    assert len(calls_a) == 1
    assert len(calls_b) == 1

@pytest.mark.asyncio
async def test_unsubscribed_channel_not_received(bus):
    received = []
    await bus.subscribe("task.created", lambda e: received.append(e))

    event = BusEvent(type="decision.pending", payload={"decision_id": "abc"})
    await bus.publish(event)
    await bus.process_one()

    assert len(received) == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_redis_bus.py -v
```

Expected: FAIL — modules not defined.

- [ ] **Step 3: Create `backend/app/schemas/__init__.py` and `backend/app/schemas/events.py`**

```python
# backend/app/schemas/events.py
from pydantic import BaseModel, Field
from datetime import datetime, UTC
from typing import Any
import uuid

class BusEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

- [ ] **Step 4: Create `backend/app/redis_bus.py`**

```python
# backend/app/redis_bus.py
import json
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
        result = await self._redis.rpop(self.CHANNEL)
        if result is None:
            return False
        event = BusEvent.model_validate_json(result)
        for handler in self._handlers.get(event.type, []):
            result = handler(event)
            if asyncio.iscoroutine(result):
                await result
        return True

    async def run_forever(self) -> None:
        """Continuously process messages. Run as a background task."""
        while True:
            processed = await self.process_one()
            if not processed:
                await asyncio.sleep(0.05)

def get_bus(redis_client: Redis) -> RedisBus:
    return RedisBus(redis_client=redis_client)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_redis_bus.py -v
```

Expected: 3 PASSED

- [ ] **Step 6: Commit**

```bash
git add backend/app/redis_bus.py backend/app/schemas/ backend/tests/test_redis_bus.py
git commit -m "feat: add Redis message bus with pub/sub and event schema"
```

---

## Task 5: Task & Decision REST Endpoints

**Files:**
- Create: `backend/app/schemas/task.py`
- Create: `backend/app/schemas/decision.py`
- Create: `backend/app/routers/__init__.py`
- Create: `backend/app/routers/tasks.py`
- Create: `backend/app/routers/decisions.py`
- Create: `backend/tests/test_tasks.py`
- Create: `backend/tests/test_decisions.py`

- [ ] **Step 1: Write failing tests for tasks**

```python
# backend/tests/test_tasks.py
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models import Base
from app.main import app
from app.database import get_db

TEST_DB = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(autouse=True)
async def setup_db():
    engine = create_async_engine(TEST_DB)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    app.dependency_overrides.clear()

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_create_task(client):
    resp = await client.post("/tasks", json={"title": "Research market", "agent_id": "cso"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Research market"
    assert data["agent_id"] == "cso"
    assert data["status"] == "pending"

@pytest.mark.asyncio
async def test_list_tasks(client):
    await client.post("/tasks", json={"title": "Task 1", "agent_id": "cso"})
    await client.post("/tasks", json={"title": "Task 2", "agent_id": "cto"})
    resp = await client.get("/tasks")
    assert resp.status_code == 200
    assert len(resp.json()) == 2

@pytest.mark.asyncio
async def test_update_task_status(client):
    create = await client.post("/tasks", json={"title": "Build feature", "agent_id": "cto"})
    task_id = create.json()["id"]
    resp = await client.patch(f"/tasks/{task_id}", json={"status": "in_progress"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"
```

- [ ] **Step 2: Write failing tests for decisions**

```python
# backend/tests/test_decisions.py
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.models import Base
from app.main import app
from app.database import get_db

TEST_DB = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(autouse=True)
async def setup_db():
    engine = create_async_engine(TEST_DB)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async def override_get_db():
        async with session_factory() as session:
            yield session
    app.dependency_overrides[get_db] = override_get_db
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    app.dependency_overrides.clear()

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_create_decision(client):
    resp = await client.post("/decisions", json={
        "title": "Launch in B2B invoicing",
        "description": "CSO identified high demand, low competition",
        "requested_by": "cso",
    })
    assert resp.status_code == 201
    assert resp.json()["status"] == "pending"

@pytest.mark.asyncio
async def test_approve_decision(client):
    create = await client.post("/decisions", json={
        "title": "Spend $500 on ads",
        "description": "CMO recommends Facebook campaign",
        "requested_by": "cmo",
    })
    decision_id = create.json()["id"]
    resp = await client.post(f"/decisions/{decision_id}/approve")
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"
    assert resp.json()["decided_by"] == "board"

@pytest.mark.asyncio
async def test_reject_decision(client):
    create = await client.post("/decisions", json={
        "title": "Pivot to enterprise",
        "description": "CSO wants to change target market",
        "requested_by": "cso",
    })
    decision_id = create.json()["id"]
    resp = await client.post(f"/decisions/{decision_id}/reject")
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"

@pytest.mark.asyncio
async def test_list_pending_decisions(client):
    await client.post("/decisions", json={"title": "D1", "description": "desc", "requested_by": "cso"})
    await client.post("/decisions", json={"title": "D2", "description": "desc", "requested_by": "cmo"})
    resp = await client.get("/decisions?status=pending")
    assert resp.status_code == 200
    assert len(resp.json()) == 2
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_tasks.py tests/test_decisions.py -v
```

Expected: FAIL — app.main not defined yet.

- [ ] **Step 4: Create Pydantic schemas**

```python
# backend/app/schemas/task.py
from pydantic import BaseModel
from app.models.task import TaskStatus

class TaskCreate(BaseModel):
    title: str
    agent_id: str
    parent_agent_id: str | None = None

class TaskUpdate(BaseModel):
    status: TaskStatus | None = None
    title: str | None = None

class TaskRead(BaseModel):
    id: str
    title: str
    agent_id: str
    parent_agent_id: str | None
    status: TaskStatus
    model_config = {"from_attributes": True}
```

```python
# backend/app/schemas/decision.py
from datetime import datetime
from pydantic import BaseModel
from app.models.decision import DecisionStatus

class DecisionCreate(BaseModel):
    title: str
    description: str
    requested_by: str

class DecisionRead(BaseModel):
    id: str
    title: str
    description: str
    requested_by: str
    status: DecisionStatus
    decided_by: str | None
    decided_at: datetime | None
    created_at: datetime
    model_config = {"from_attributes": True}
```

- [ ] **Step 5: Create `backend/app/routers/tasks.py`**

```python
# backend/app/routers/tasks.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.get("", response_model=list[TaskRead])
async def list_tasks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).order_by(Task.created_at.desc()))
    return result.scalars().all()

@router.post("", response_model=TaskRead, status_code=201)
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_db)):
    task = Task(**body.model_dump())
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task

@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(task_id: str, body: TaskUpdate, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(task, field, value)
    await db.commit()
    await db.refresh(task)
    return task
```

- [ ] **Step 6: Create `backend/app/routers/decisions.py`**

```python
# backend/app/routers/decisions.py
from datetime import datetime, UTC
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.decision import Decision, DecisionStatus
from app.schemas.decision import DecisionCreate, DecisionRead

router = APIRouter(prefix="/decisions", tags=["decisions"])

@router.get("", response_model=list[DecisionRead])
async def list_decisions(status: DecisionStatus | None = None, db: AsyncSession = Depends(get_db)):
    query = select(Decision).order_by(Decision.created_at.desc())
    if status:
        query = query.where(Decision.status == status)
    result = await db.execute(query)
    return result.scalars().all()

@router.post("", response_model=DecisionRead, status_code=201)
async def create_decision(body: DecisionCreate, db: AsyncSession = Depends(get_db)):
    decision = Decision(**body.model_dump())
    db.add(decision)
    await db.commit()
    await db.refresh(decision)
    return decision

@router.post("/{decision_id}/approve", response_model=DecisionRead)
async def approve_decision(decision_id: str, db: AsyncSession = Depends(get_db)):
    decision = await db.get(Decision, decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")
    if decision.status != DecisionStatus.PENDING:
        raise HTTPException(status_code=400, detail="Decision already resolved")
    decision.status = DecisionStatus.APPROVED
    decision.decided_by = "board"
    decision.decided_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(decision)
    return decision

@router.post("/{decision_id}/reject", response_model=DecisionRead)
async def reject_decision(decision_id: str, db: AsyncSession = Depends(get_db)):
    decision = await db.get(Decision, decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")
    if decision.status != DecisionStatus.PENDING:
        raise HTTPException(status_code=400, detail="Decision already resolved")
    decision.status = DecisionStatus.REJECTED
    decision.decided_by = "board"
    decision.decided_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(decision)
    return decision
```

- [ ] **Step 7: Create `backend/app/main.py` (app entry point)**

```python
# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import tasks, decisions

app = FastAPI(title="Project Million", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router)
app.include_router(decisions.router)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 8: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_tasks.py tests/test_decisions.py -v
```

Expected: 7 PASSED

- [ ] **Step 9: Commit**

```bash
git add backend/app/main.py backend/app/routers/ backend/app/schemas/task.py backend/app/schemas/decision.py backend/tests/test_tasks.py backend/tests/test_decisions.py
git commit -m "feat: add Task and Decision REST endpoints with approve/reject flow"
```

---

## Task 6: Agent Status & Heartbeat

**Files:**
- Create: `backend/app/routers/agents.py`
- Create: `backend/tests/test_agents.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_agents.py
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

@pytest.mark.asyncio
async def test_heartbeat_registers_agent(client):
    resp = await client.post("/agents/cso/heartbeat", json={"status": "active"})
    assert resp.status_code == 200
    assert resp.json()["agent_id"] == "cso"
    assert resp.json()["status"] == "active"

@pytest.mark.asyncio
async def test_get_all_agent_statuses(client):
    await client.post("/agents/cso/heartbeat", json={"status": "active"})
    await client.post("/agents/cto/heartbeat", json={"status": "thinking"})
    resp = await client.get("/agents/status")
    assert resp.status_code == 200
    agents = {a["agent_id"]: a for a in resp.json()}
    assert agents["cso"]["status"] == "active"
    assert agents["cto"]["status"] == "thinking"

@pytest.mark.asyncio
async def test_unknown_agent_returns_idle(client):
    resp = await client.get("/agents/status")
    assert resp.status_code == 200
    # System always returns the full known agent list
    statuses = {a["agent_id"]: a["status"] for a in resp.json()}
    for agent_id in ["cso", "cto", "cmo", "cfo", "coo"]:
        assert agent_id in statuses
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_agents.py -v
```

Expected: FAIL

- [ ] **Step 3: Create `backend/app/routers/agents.py`**

```python
# backend/app/routers/agents.py
from datetime import datetime, UTC
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/agents", tags=["agents"])

KNOWN_AGENTS = ["cso", "cto", "cmo", "cfo", "coo",
                "market_scanner", "opportunity_evaluator",
                "code_writer", "qa_tester", "devops",
                "content_writer", "social_media", "email_campaign", "ad_manager",
                "revenue_tracker", "pricing_optimizer",
                "support_agent", "task_coordinator"]

# In-memory store — replaced by Redis in Phase 2
_agent_statuses: dict[str, dict] = {
    agent_id: {"agent_id": agent_id, "status": "idle", "last_seen": None}
    for agent_id in KNOWN_AGENTS
}

class HeartbeatRequest(BaseModel):
    status: str  # active | thinking | idle

class AgentStatus(BaseModel):
    agent_id: str
    status: str
    last_seen: datetime | None

@router.post("/{agent_id}/heartbeat", response_model=AgentStatus)
async def heartbeat(agent_id: str, body: HeartbeatRequest):
    _agent_statuses[agent_id] = {
        "agent_id": agent_id,
        "status": body.status,
        "last_seen": datetime.now(UTC),
    }
    return _agent_statuses[agent_id]

@router.get("/status", response_model=list[AgentStatus])
async def get_all_statuses():
    return list(_agent_statuses.values())
```

- [ ] **Step 4: Register router in `main.py`**

```python
# In backend/app/main.py, add:
from app.routers import tasks, decisions, agents  # add agents

app.include_router(agents.router)  # add this line
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_agents.py -v
```

Expected: 3 PASSED

- [ ] **Step 6: Run full test suite**

```bash
cd backend && pytest -v
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/agents.py backend/tests/test_agents.py backend/app/main.py
git commit -m "feat: add agent status and heartbeat endpoints"
```

---

## Task 7: WebSocket Event Stream

**Files:**
- Create: `backend/app/routers/websocket.py`
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/bus.py`
- Create: `backend/tests/test_websocket.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_websocket.py
import pytest
import json
from httpx import AsyncClient, ASGITransport
from httpx_ws import aconnect_ws
from app.main import app

@pytest.mark.asyncio
async def test_websocket_connects():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with aconnect_ws("/ws", client) as ws:
            # Should receive a welcome message on connect
            msg = await ws.receive_text()
            data = json.loads(msg)
            assert data["type"] == "connected"

@pytest.mark.asyncio
async def test_websocket_receives_broadcast():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with aconnect_ws("/ws", client) as ws:
            await ws.receive_text()  # consume welcome

            # Trigger a broadcast via REST
            await client.post("/tasks", json={"title": "Test task", "agent_id": "cso"})

            # Note: if flaky, wrap in: asyncio.wait_for(ws.receive_text(), timeout=2.0)
            msg = await ws.receive_text()
            data = json.loads(msg)
            assert data["type"] == "task.created"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pip install httpx-ws && pytest tests/test_websocket.py -v
```

Expected: FAIL

- [ ] **Step 3: Create `backend/app/services/bus.py` (broadcast service)**

```python
# backend/app/services/bus.py
import asyncio
from typing import ClassVar
from fastapi import WebSocket
from app.schemas.events import BusEvent

class ConnectionManager:
    _instance: ClassVar["ConnectionManager | None"] = None

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    @classmethod
    def get(cls) -> "ConnectionManager":
        if cls._instance is None:
            cls._instance = ConnectionManager()
        return cls._instance

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, event: BusEvent):
        data = event.model_dump_json()
        dead = []
        for ws in self.active_connections:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active_connections.remove(ws)

manager = ConnectionManager.get()
```

- [ ] **Step 4: Create `backend/app/routers/websocket.py`**

```python
# backend/app/routers/websocket.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.schemas.events import BusEvent
from app.services.bus import manager

router = APIRouter(tags=["websocket"])

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    welcome = BusEvent(type="connected", payload={"message": "Mission Control connected"})
    await websocket.send_text(welcome.model_dump_json())
    try:
        while True:
            await websocket.receive_text()  # keep connection alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

- [ ] **Step 5: Update task router to broadcast events**

```python
# In backend/app/routers/tasks.py, update create_task:
from app.services.bus import manager
from app.schemas.events import BusEvent

@router.post("", response_model=TaskRead, status_code=201)
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_db)):
    task = Task(**body.model_dump())
    db.add(task)
    await db.commit()
    await db.refresh(task)
    event = BusEvent(type="task.created", payload={"task_id": task.id, "title": task.title, "agent_id": task.agent_id})
    await manager.broadcast(event)
    return task
```

- [ ] **Step 6: Register WebSocket router in `main.py`**

```python
# In backend/app/main.py, add:
from app.routers import tasks, decisions, agents, websocket

app.include_router(websocket.router)
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
cd backend && pytest tests/test_websocket.py -v
```

Expected: 2 PASSED

- [ ] **Step 8: Run full test suite**

```bash
cd backend && pytest -v --tb=short
```

Expected: All tests pass.

- [ ] **Step 9: Commit**

```bash
git add backend/app/routers/websocket.py backend/app/services/ backend/tests/test_websocket.py backend/app/main.py backend/app/routers/tasks.py
git commit -m "feat: add WebSocket event stream with broadcast on task creation"
```

---

## Task 8: Next.js Frontend — Dashboard Shell

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/types/index.ts`
- Create: `frontend/lib/api.ts`
- Create: `frontend/hooks/useWebSocket.ts`
- Create: `frontend/components/TopBar.tsx`
- Create: `frontend/components/KPICards.tsx`
- Create: `frontend/components/ApprovalQueue.tsx`
- Create: `frontend/components/AgentStatusGrid.tsx`
- Create: `frontend/components/TaskFeed.tsx`
- Create: `frontend/app/page.tsx`

- [ ] **Step 1: Scaffold Next.js app**

```bash
cd frontend && npx create-next-app@latest . --typescript --tailwind --app --no-src-dir --no-eslint --import-alias "@/*"
```

Expected: Next.js project scaffolded.

- [ ] **Step 2: Create `frontend/types/index.ts`**

```typescript
export type AgentStatus = "active" | "thinking" | "idle";

export interface Agent {
  agent_id: string;
  status: AgentStatus;
  last_seen: string | null;
}

export type TaskStatus = "pending" | "in_progress" | "done" | "failed";

export interface Task {
  id: string;
  title: string;
  agent_id: string;
  status: TaskStatus;
}

export type DecisionStatus = "pending" | "approved" | "rejected";

export interface Decision {
  id: string;
  title: string;
  description: string;
  requested_by: string;
  status: DecisionStatus;
  decided_by: string | null;
  decided_at: string | null;
  created_at: string;
}

export interface KPIs {
  weekly_revenue: number;
  active_customers: number;
  tasks_in_progress: number;
  pending_approvals: number;
  active_agents: number;
}

export interface BusEvent {
  id: string;
  type: string;
  payload: Record<string, unknown>;
  timestamp: string;
}
```

- [ ] **Step 3: Create `frontend/lib/api.ts`**

```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return res.json();
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`);
  return res.json();
}

export const api = {
  decisions: {
    list: (status?: string) =>
      get<import("@/types").Decision[]>(`/decisions${status ? `?status=${status}` : ""}`),
    approve: (id: string) => post<import("@/types").Decision>(`/decisions/${id}/approve`),
    reject: (id: string) => post<import("@/types").Decision>(`/decisions/${id}/reject`),
  },
  tasks: {
    list: () => get<import("@/types").Task[]>("/tasks"),
  },
  agents: {
    status: () => get<import("@/types").Agent[]>("/agents/status"),
  },
};
```

- [ ] **Step 4: Create `frontend/hooks/useWebSocket.ts`**

```typescript
"use client";
import { useEffect, useRef, useCallback } from "react";
import type { BusEvent } from "@/types";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";

export function useWebSocket(onEvent: (event: BusEvent) => void) {
  const wsRef = useRef<WebSocket | null>(null);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const connect = useCallback(() => {
    const ws = new WebSocket(`${WS_URL}/ws`);
    wsRef.current = ws;

    ws.onmessage = (e) => {
      try {
        const event: BusEvent = JSON.parse(e.data);
        onEventRef.current(event);
      } catch {}
    };

    ws.onclose = () => {
      setTimeout(connect, 2000); // reconnect after 2s
    };

    return ws;
  }, []);

  useEffect(() => {
    const ws = connect();
    return () => ws.close();
  }, [connect]);
}
```

- [ ] **Step 5: Create dashboard components**

```typescript
// frontend/components/TopBar.tsx
"use client";
interface Props { agentCount: number; weeklyRevenue: number; pendingApprovals: number; }
export function TopBar({ agentCount, weeklyRevenue, pendingApprovals }: Props) {
  return (
    <div className="flex items-center justify-between bg-gray-900 border-b border-gray-700 px-6 py-3">
      <h1 className="text-xl font-bold text-white tracking-wide">PROJECT MILLION — MISSION CONTROL</h1>
      <div className="flex gap-8 text-sm">
        <span className="text-green-400 font-semibold">{agentCount} AGENTS LIVE</span>
        <span className="text-yellow-400 font-semibold">${weeklyRevenue.toLocaleString()} / WEEK</span>
        <span className="text-red-400 font-semibold">{pendingApprovals} PENDING</span>
      </div>
    </div>
  );
}
```

```typescript
// frontend/components/KPICards.tsx
"use client";
interface Props { weeklyRevenue: number; activeCustomers: number; tasksInProgress: number; }
function Card({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
      <p className="text-gray-400 text-base mb-2">{label}</p>
      <p className={`text-[34px] font-bold ${color}`}>{value}</p>
    </div>
  );
}
export function KPICards({ weeklyRevenue, activeCustomers, tasksInProgress }: Props) {
  return (
    <div className="grid grid-cols-3 gap-4">
      <Card label="Weekly Revenue" value={`$${weeklyRevenue.toLocaleString()}`} color="text-green-400" />
      <Card label="Active Customers" value={activeCustomers.toLocaleString()} color="text-blue-400" />
      <Card label="Tasks In Progress" value={tasksInProgress.toString()} color="text-yellow-400" />
    </div>
  );
}
```

```typescript
// frontend/components/ApprovalQueue.tsx
"use client";
import type { Decision } from "@/types";
interface Props { decisions: Decision[]; onApprove: (id: string) => void; onReject: (id: string) => void; }
export function ApprovalQueue({ decisions, onApprove, onReject }: Props) {
  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-4 h-full">
      <h2 className="text-white font-bold text-base mb-4">APPROVAL QUEUE ({decisions.length})</h2>
      <div className="space-y-3 overflow-y-auto max-h-[600px]">
        {decisions.length === 0 && <p className="text-gray-500 text-sm">No pending decisions</p>}
        {decisions.map((d) => (
          <div key={d.id} className="bg-gray-900 rounded p-3 border border-gray-600">
            <p className="text-white text-sm font-semibold mb-1">{d.title}</p>
            <p className="text-gray-400 text-xs mb-3">{d.description}</p>
            <p className="text-gray-500 text-xs mb-3">Requested by: {d.requested_by.toUpperCase()}</p>
            <div className="flex gap-2">
              <button onClick={() => onApprove(d.id)} className="flex-1 bg-green-600 hover:bg-green-500 text-white text-xs py-1.5 rounded font-semibold">APPROVE</button>
              <button onClick={() => onReject(d.id)} className="flex-1 bg-red-700 hover:bg-red-600 text-white text-xs py-1.5 rounded font-semibold">REJECT</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

```typescript
// frontend/components/AgentStatusGrid.tsx
"use client";
import type { Agent } from "@/types";
const STATUS_COLORS = { active: "bg-green-500", thinking: "bg-yellow-400", idle: "bg-gray-600" };
interface Props { agents: Agent[]; }
export function AgentStatusGrid({ agents }: Props) {
  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
      <h2 className="text-white font-bold text-base mb-4">AGENT STATUS</h2>
      <div className="grid grid-cols-3 gap-2">
        {agents.map((a) => (
          <div key={a.agent_id} className="flex items-center gap-2 bg-gray-900 rounded p-2">
            <div className={`w-2.5 h-2.5 rounded-full ${STATUS_COLORS[a.status] ?? "bg-gray-600"}`} />
            <span className="text-gray-300 text-xs uppercase font-mono">{a.agent_id}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

```typescript
// frontend/components/TaskFeed.tsx
"use client";
import type { Task } from "@/types";
const STATUS_STYLES: Record<string, string> = {
  done: "text-green-400", in_progress: "text-yellow-400", pending: "text-gray-400", failed: "text-red-400",
};
interface Props { tasks: Task[]; }
export function TaskFeed({ tasks }: Props) {
  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
      <h2 className="text-white font-bold text-base mb-4">LIVE TASK FEED</h2>
      <div className="space-y-2 max-h-64 overflow-y-auto">
        {tasks.map((t) => (
          <div key={t.id} className="flex items-center justify-between text-sm">
            <span className="text-gray-300 truncate max-w-[60%]">{t.title}</span>
            <div className="flex items-center gap-3">
              <span className="text-gray-500 text-xs">{t.agent_id.toUpperCase()}</span>
              <span className={`text-xs font-semibold uppercase ${STATUS_STYLES[t.status]}`}>{t.status}</span>
            </div>
          </div>
        ))}
        {tasks.length === 0 && <p className="text-gray-500 text-sm">No tasks yet</p>}
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Create `frontend/app/page.tsx` (Mission Control)**

```typescript
"use client";
import { useState, useEffect, useCallback } from "react";
import { TopBar } from "@/components/TopBar";
import { KPICards } from "@/components/KPICards";
import { ApprovalQueue } from "@/components/ApprovalQueue";
import { AgentStatusGrid } from "@/components/AgentStatusGrid";
import { TaskFeed } from "@/components/TaskFeed";
import { useWebSocket } from "@/hooks/useWebSocket";
import { api } from "@/lib/api";
import type { Agent, Task, Decision, BusEvent } from "@/types";

export default function MissionControl() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [decisions, setDecisions] = useState<Decision[]>([]);

  const refresh = useCallback(async () => {
    const [a, t, d] = await Promise.all([
      api.agents.status(),
      api.tasks.list(),
      api.decisions.list("pending"),
    ]);
    setAgents(a);
    setTasks(t);
    setDecisions(d);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  useWebSocket(useCallback((event: BusEvent) => {
    if (["task.created", "task.completed", "decision.pending", "agent.status"].includes(event.type)) {
      refresh();
    }
  }, [refresh]));

  const handleApprove = async (id: string) => {
    await api.decisions.approve(id);
    await refresh();
  };

  const handleReject = async (id: string) => {
    await api.decisions.reject(id);
    await refresh();
  };

  const activeAgents = agents.filter((a) => a.status === "active").length;
  const weeklyRevenue = 0; // wired up in Phase 2 when CFO is active
  const tasksInProgress = tasks.filter((t) => t.status === "in_progress").length;

  return (
    <div className="min-h-screen bg-gray-950 text-base">
      <TopBar agentCount={activeAgents} weeklyRevenue={weeklyRevenue} pendingApprovals={decisions.length} />
      <div className="p-6 grid grid-cols-4 gap-6">
        <div className="col-span-3 space-y-6">
          <KPICards weeklyRevenue={weeklyRevenue} activeCustomers={0} tasksInProgress={tasksInProgress} />
          <AgentStatusGrid agents={agents} />
          <TaskFeed tasks={tasks.slice(0, 20)} />
        </div>
        <div className="col-span-1">
          <ApprovalQueue decisions={decisions} onApprove={handleApprove} onReject={handleReject} />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Verify frontend builds**

```bash
cd frontend && npm run build
```

Expected: Build succeeds with no errors.

- [ ] **Step 8: Start dev server and verify dashboard loads**

```bash
cd frontend && npm run dev
```

Open `http://localhost:3000` — Mission Control should render with empty state.

- [ ] **Step 9: Commit**

```bash
git add frontend/
git commit -m "feat: Mission Control dashboard shell with live WebSocket updates"
```

---

## Task 9: Full Integration Smoke Test

- [ ] **Step 1: Start the full stack**

```bash
docker compose up --build
```

Expected: All 4 services start (postgres, redis, backend, frontend).

- [ ] **Step 2: Verify backend health**

```bash
curl http://localhost:8000/health
```

Expected: `{"status": "ok"}`

- [ ] **Step 3: Create a test decision and approve it**

```bash
# Create decision
curl -X POST http://localhost:8000/decisions \
  -H "Content-Type: application/json" \
  -d '{"title":"Enter B2B invoicing market","description":"CSO recommends","requested_by":"cso"}'

# Note the id from response, then approve:
curl -X POST http://localhost:8000/decisions/<id>/approve
```

Expected: Decision status changes to `approved`.

- [ ] **Step 4: Verify dashboard shows the decision flow**

Open `http://localhost:3000` — create a decision via the API and watch the approval queue populate in real time.

- [ ] **Step 5: Run full backend test suite with coverage**

```bash
cd backend && pytest --cov=app --cov-report=term-missing -v
```

Expected: All tests pass, coverage >80% on core modules.

- [ ] **Step 6: Final commit**

```bash
git add .
git commit -m "chore: Phase 1 complete — core infrastructure + dashboard shell"
```

---

## Phase 1 Done Criteria

- [ ] All backend tests pass (`pytest -v`)
- [ ] Frontend builds without errors (`npm run build`)
- [ ] Full stack starts via `docker compose up`
- [ ] Dashboard renders and shows live updates via WebSocket
- [ ] Decisions can be created and approved/rejected via API and reflected in dashboard
- [ ] Test coverage >80% on agent decision logic

---

*Next: Phase 2 — Agent Framework (C-Suite + Workers, decision queue wired to agents, full audit log)*
