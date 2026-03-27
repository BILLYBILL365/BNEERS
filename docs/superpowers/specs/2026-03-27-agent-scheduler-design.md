# Agent Scheduler Design

**Date:** 2026-03-27
**Status:** Approved

---

## Goal

Automatically kick off a new business cycle every 6 hours (configurable), and allow the Board to manually trigger a cycle from Mission Control. One cycle runs at a time — the scheduler skips if a cycle is already in progress.

---

## Architecture

A single new component — `AgentScheduler` — runs inside the existing FastAPI/uvicorn process as an asyncio background task, alongside the `AgentRunner` and Redis bus loop already started in `main.py`.

```
main.py lifespan
├── AgentRunner          (existing — owns C-Suite agents)
├── AgentScheduler       (new — owns schedule loop + cycle state)
└── RedisBus loop        (existing — event pump)
```

The scheduler communicates with agents exclusively through the Redis bus (publishes `cycle.start`). It also subscribes to `decision.approved` and `decision.rejected` to know when a cycle has resolved.

---

## Cycle Flow

### Automatic (scheduled)
1. `AgentScheduler._loop()` wakes up every `CYCLE_INTERVAL_SECONDS`
2. Calls `trigger()` — skips if `_cycle_running` is True
3. Sets `_cycle_running = True`, records `_cycle_started_at`
4. Publishes `cycle.start` on the bus
5. CSO receives `cycle.start`, runs market research, posts a Board decision
6. Board approves or rejects in Mission Control
7. `_on_cycle_resolved()` fires (subscribed to `decision.approved` / `decision.rejected`)
8. Resets `_cycle_running = False`

### Manual (Board-initiated)
- `POST /cycles/trigger` calls `AgentScheduler.trigger()` directly
- Returns `{"started": true}` if cycle began
- Returns `{"started": false, "reason": "cycle already running"}` if skipped (HTTP 200 — not an error)

### Skip path
`trigger()` checks `_cycle_running` before doing anything. If True: logs to audit (`cycle_skipped`), returns False, does nothing else.

### Timeout / safety reset
When a cycle starts, a 4-hour `asyncio.Task` is created. If it fires before `_on_cycle_resolved()`:
- Resets `_cycle_running = False`
- Publishes `agent.alert` on the bus (Discord alert fires via King Solomon)
- Logs `cycle_timeout` to audit

### Error handling
Any exception inside `_loop()` is caught, logged to audit (`cycle_error`), and the loop resumes after the next interval. The loop never crashes the process.

---

## Components & File Changes

### New files

**`backend/app/scheduler.py`**
```python
class AgentScheduler:
    async def start(self) -> None        # begins _loop as asyncio.Task
    async def stop(self) -> None         # cancels loop + timeout task
    async def trigger(self) -> bool      # True=started, False=skipped
    async def _loop(self) -> None        # sleep(interval) → trigger() → repeat
    async def _on_cycle_resolved(self, event: BusEvent) -> None  # resets flag
    async def _on_timeout(self) -> None  # 4-hour safety reset
```

Constructor args: `bus: RedisBus`, `audit: AuditService`, `interval_seconds: int`

### Modified files

**`backend/app/agents/cso.py`**
- Add `await self.subscribe("cycle.start", self._on_cycle_start)` in `on_start()`
- Add `_on_cycle_start()` handler that calls `_run_market_research()`

**`backend/app/main.py`**
- Instantiate `AgentScheduler(bus, audit, interval_seconds=settings.CYCLE_INTERVAL_SECONDS)`
- Subscribe scheduler to `decision.approved` and `decision.rejected`
- Start scheduler after `runner.start()`
- Cancel scheduler task on shutdown (alongside `bus_task`)

**`backend/app/config.py`**
- Add `CYCLE_INTERVAL_SECONDS: int = 21600`

**`backend/app/routers/agents.py`**
- Add `POST /cycles/trigger` endpoint
- Returns `CycleTriggerResponse(started: bool, reason: str | None)`
- Needs access to the scheduler singleton (same pattern as `set_bus()` in decisions router)

**`frontend/lib/api.ts`**
- Add `cycles: { trigger: () => post<CycleTriggerResponse>("/cycles/trigger") }`

**`frontend/app/page.tsx`**
- Add "▶ Start Cycle" button in the top bar or near KPI cards
- Button calls `api.cycles.trigger()` and shows a brief status toast (started / already running)
- No new state needed beyond the existing `refresh()` call after trigger

---

## API

### `POST /cycles/trigger`

**Response (always 200):**
```json
{"started": true}
// or
{"started": false, "reason": "cycle already running"}
```

---

## New Bus Events

| Event | Published by | Meaning |
|-------|-------------|---------|
| `cycle.start` | AgentScheduler | New cycle beginning — CSO should run |
| `agent.alert` | AgentScheduler | Cycle timed out after 4 hours |

Existing events used:
- `decision.approved` — scheduler subscribes to detect cycle resolution
- `decision.rejected` — scheduler subscribes to detect cycle resolution

---

## Configuration

| Env var | Default | Description |
|---------|---------|-------------|
| `CYCLE_INTERVAL_SECONDS` | `21600` | How often the scheduler fires (seconds). 21600 = 6 hours. |

Add to `.env.example` and `.env.production.example`.

---

## Testing

- Unit test `AgentScheduler.trigger()`: skip when `_cycle_running=True`, start when False
- Unit test `_on_cycle_resolved()`: resets `_cycle_running`, cancels timeout task
- Unit test `_on_timeout()`: resets flag, publishes `agent.alert`
- Integration test: `POST /cycles/trigger` → 200 `{"started": true}`
- Integration test: second `POST /cycles/trigger` while running → `{"started": false}`
- CSO unit test: `cycle.start` event triggers `_run_market_research()`
