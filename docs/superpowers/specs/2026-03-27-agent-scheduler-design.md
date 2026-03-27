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

The scheduler communicates with agents exclusively through the Redis bus. It publishes `cycle.start` (with a `cycle_id`) to begin a cycle. The CSO echoes the `cycle_id` back when it is done by publishing `cycle.completed`. The scheduler subscribes to `cycle.completed` (not `decision.approved`/`decision.rejected`) to know when a cycle has resolved — this prevents mid-cycle decisions (e.g. `approve_opportunity`) from falsely resetting the running flag.

---

## Cycle Flow

### Automatic (scheduled)
1. `AgentScheduler._loop()` sleeps for `CYCLE_INTERVAL_SECONDS`, **then** calls `trigger()`. The first cycle fires after the first full interval — not immediately on startup. This is intentional: startup may still be settling, and manual trigger is available for immediate execution.
2. Calls `trigger()` — skips if `_cycle_running` is True
3. Sets `_cycle_running = True`, generates a `cycle_id` (UUID4), stores as `_current_cycle_id`
4. Publishes `cycle.start` with `{"cycle_id": "<uuid>"}` on the bus
5. CSO's `_on_cycle_start()` stores `cycle_id`, calls `_run_market_research()` (which posts an `approve_opportunity` decision and returns immediately)
6. Board approves or rejects the `approve_opportunity` decision in Mission Control
7. CSO's `_on_opportunity_approved()` or `_on_decision_rejected()` fires; if `_current_cycle_id` is set, publishes `cycle.completed` with `{"cycle_id": "<uuid>", "outcome": "approved"|"rejected"}` and clears `_current_cycle_id`
8. `AgentScheduler._on_cycle_completed()` checks `cycle_id` matches `_current_cycle_id`, resets `_cycle_running = False`, cancels the timeout task

### Manual (Board-initiated)
- `POST /cycles/trigger` calls `AgentScheduler.trigger()` directly
- Returns `{"started": true}` if cycle began
- Returns `{"started": false, "reason": "cycle already running"}` if skipped (HTTP 200 — not an error)

### Skip path
`trigger()` checks `_cycle_running` before doing anything. If True: logs `cycle_skipped` to audit, returns False.

### Timeout / safety reset
When a cycle starts, a 4-hour `asyncio.Task` (`_timeout_task`) is created. If it fires before `_on_cycle_completed()`:
- Resets `_cycle_running = False`
- Clears `_timeout_task` to `None`
- Publishes `agent.alert` on the bus (Discord alert fires via King Solomon — payload matches existing King Solomon contract: `{"agent_id": "scheduler", "reason": "cycle_timeout", "message": "Cycle timed out after 4 hours"}`)
- Logs `cycle_timeout` to audit

`_on_cycle_completed()` always cancels `_timeout_task` when it fires — even after a clean resolution — so the timeout never fires on a resolved cycle. Before cancelling, check `if self._timeout_task and not self._timeout_task.done()` to guard against a `None` task (e.g. `trigger()` was never called) or a task that already completed.

**Race condition handling:** Both `_on_cycle_completed()` and `_on_timeout()` must begin with `if not self._cycle_running: return` to guard against double-execution. Because asyncio is single-threaded and task cancellation is only checked at `await` points, calling `self._timeout_task.cancel()` synchronously (before any `await`) inside `_on_cycle_completed()` prevents `_on_timeout` from advancing past its next `await`. The `if not self._cycle_running: return` guard at the top of both handlers ensures that even if both fire, only the first one resets state.

### Error handling
Any exception inside `_loop()` is caught, logged as `cycle_error` to audit, and the loop resumes after the next interval. The loop never crashes the process.

---

## Components & File Changes

### New files

**`backend/app/scheduler.py`**
```python
_scheduler: AgentScheduler | None = None

def set_scheduler(scheduler: AgentScheduler) -> None:
    global _scheduler
    _scheduler = scheduler

def get_scheduler() -> AgentScheduler | None:
    return _scheduler

class AgentScheduler:
    _cycle_running: bool           # True while a cycle is in progress
    _current_cycle_id: str | None  # UUID of the in-progress cycle; None when idle
    _loop_task: asyncio.Task | None
    _timeout_task: asyncio.Task | None

    def __init__(self, bus: RedisBus, audit: AuditService, interval_seconds: int) -> None: ...
    async def start(self) -> None        # registers subscriptions, begins _loop as asyncio.Task
    async def stop(self) -> None         # cancels _loop_task and _timeout_task; awaits cancellation; swallows CancelledError
    async def trigger(self) -> bool      # True=started (sets _cycle_running, stores _current_cycle_id, publishes cycle.start), False=skipped
    async def _loop(self) -> None        # sleep(interval) → trigger() → repeat; catches all exceptions, logs cycle_error, never raises
    async def _on_cycle_completed(self, event: BusEvent) -> None  # validates cycle_id matches _current_cycle_id, resets flag, cancels timeout
    async def _on_timeout(self) -> None  # 4-hour safety reset; resets flag, clears _timeout_task, publishes agent.alert
```

`start()` registers its own subscriptions internally (`cycle.completed`) — consistent with how `AgentRunner` and `DiscordNotifier` register subscriptions in their own `start()` methods, not in `main.py`.

`stop()` must `await` cancellation of both tasks and swallow `asyncio.CancelledError`. The scheduler is stopped **before** the bus is torn down (see Shutdown Order), so if `_timeout_task` fires mid-cancellation it may still successfully publish `agent.alert` on the bus — this is acceptable and expected behavior.

### New files (continued)

**`backend/app/routers/cycles.py`**
- `POST /cycles/trigger` endpoint (cleaner than bolting onto `agents.py`)
- Calls `get_scheduler().trigger()`
- Returns `CycleTriggerResponse(started: bool, reason: str | None = None)`
- If scheduler is not initialized, returns `{"started": false, "reason": "scheduler not initialized"}`

### Modified files

**`backend/app/agents/cso.py`**

CSO adds a `_current_cycle_id: str | None = None` instance attribute (None when not in a scheduler-initiated cycle).

**Important architecture note:** `_run_market_research()` returns `None` immediately after calling `request_decision()` (which posts the `approve_opportunity` decision and returns). It does **not** await the Board's response. The Board's decision arrives later as a separate bus event. Therefore `cycle.completed` cannot be published from `_on_cycle_start()` — it must be published from the handlers that process the Board's ultimate decision on the `approve_opportunity` proposal.

- In `on_start()`: add `await self.subscribe("cycle.start", self._on_cycle_start)`
- Add `_on_cycle_start(event)` handler:
  1. Guard: `if self._current_cycle_id is not None: log warning, return` (ignore duplicate `cycle.start` while a cycle is already being tracked)
  2. Store `self._current_cycle_id = event.payload["cycle_id"]`
  3. Call `await self._run_market_research()` (posts `approve_opportunity` decision and returns — cycle is still in progress)
  4. Do **not** publish `cycle.completed` here — the cycle is not done yet

- Modify `_on_opportunity_approved(event)` (the existing handler for `decision.approved / task=="approve_opportunity"`):
  - After the existing logic, add: `if self._current_cycle_id is not None: publish cycle.completed with {"cycle_id": self._current_cycle_id, "outcome": "approved"}; set self._current_cycle_id = None`

- Modify `_on_decision_rejected(event)` (the existing handler for all `decision.rejected` events):
  - After the existing log, add: `if self._current_cycle_id is not None: publish cycle.completed with {"cycle_id": self._current_cycle_id, "outcome": "rejected"}; set self._current_cycle_id = None`

- The existing `decision.approved / task=="market_research"` path (manual Board trigger for market research) remains unchanged. Add guard: `if self._current_cycle_id is not None: return` before calling `_run_market_research()` in this branch — prevents a manual Board override from conflicting with an in-progress scheduler cycle.

**Summary of two paths:**
| Path | Triggers `_run_market_research` | Sets `_current_cycle_id` | Publishes `cycle.completed` |
|------|--------------------------------|--------------------------|-----------------------------|
| Scheduler (`cycle.start`) | Yes, from `_on_cycle_start` | Yes | Yes, from `_on_opportunity_approved` / `_on_decision_rejected` |
| Manual Board (`decision.approved / task=market_research`) | Yes, from `_on_decision_approved` (only if `_current_cycle_id is None`) | No | No |

**`backend/app/main.py`**
- Add `from app.scheduler import AgentScheduler, set_scheduler`
- Add `from app.routers import cycles` (include router)
- After `runner.start()`: instantiate `AgentScheduler`, call `set_scheduler(scheduler)`, call `await scheduler.start()`
- Shutdown order: stop scheduler **before** cancelling `bus_task` (scheduler may publish `agent.alert` on timeout during shutdown)
- `app.include_router(cycles.router)`

**`backend/app/config.py`**
- Add `CYCLE_INTERVAL_SECONDS: int = 21600`

**`.env.example`**
- Add `CYCLE_INTERVAL_SECONDS=21600`

**`.env.production.example`**
- Add `CYCLE_INTERVAL_SECONDS=21600`

**`frontend/lib/api.ts`**
- Add `cycles: { trigger: () => post<{ started: boolean; reason?: string }>("/cycles/trigger") }`

**`frontend/app/page.tsx`**
- Add "▶ Start Cycle" button in the top bar area
- On click: disable the button immediately and show a loading indicator while awaiting the response
- After response arrives, re-enable the button and show inline status for 3 seconds:
  - If `response.started === true`: display `"Cycle started"`
  - If `response.started === false`: display the `response.reason` string from the API (e.g. `"cycle already running"` or `"scheduler not initialized"`)
- No new persistent state needed

---

## API

### `POST /cycles/trigger`

**Response (always 200):**
```json
{"started": true}
// or
{"started": false, "reason": "cycle already running"}
// or
{"started": false, "reason": "scheduler not initialized"}
```

---

## New Bus Events

| Event | Published by | Payload | Meaning |
|-------|-------------|---------|---------|
| `cycle.start` | AgentScheduler | `{"cycle_id": "<uuid>"}` | New cycle beginning — CSO should run |
| `cycle.completed` | CSO | `{"cycle_id": "<uuid>", "outcome": "approved"\|"rejected"}` | CSO has finished its cycle work |
| `agent.alert` | AgentScheduler | `{"agent_id": "scheduler", "reason": "cycle_timeout", "message": "Cycle timed out after 4 hours"}` | Cycle timed out after 4 hours — King Solomon's existing `agent.alert` handler must accept this payload shape (same `agent_id`/`reason`/`message` fields used by other alert publishers) |

---

## Configuration

| Env var | Default | Description |
|---------|---------|-------------|
| `CYCLE_INTERVAL_SECONDS` | `21600` | How often the scheduler fires (seconds). 21600 = 6 hours. |

---

## Shutdown Order

```
1. await scheduler.stop()     # cancel loop + timeout task; no more cycle.start events
2. bus_task.cancel()          # stop event pump
3. await runner.stop()        # stop agents
4. await notifier.stop()      # stop Discord bot
5. await redis_client.aclose()
```

Scheduler is stopped first so it cannot publish during teardown after the bus is gone.

---

## Testing

- Unit: `trigger()` returns False and logs `cycle_skipped` when `_cycle_running=True`
- Unit: `trigger()` returns True, sets `_cycle_running=True`, publishes `cycle.start` when False
- Unit: `_on_cycle_completed()` resets `_cycle_running`, cancels timeout task
- Unit: `_on_cycle_completed()` ignores events with non-matching `cycle_id`
- Unit: `_on_timeout()` resets flag, publishes `agent.alert`, logs `cycle_timeout`
- Unit: `_on_cycle_completed()` called while `_timeout_task` is still pending — verifies timeout task is cancelled and does not subsequently reset `_cycle_running`
- Unit: `_on_cycle_completed()` called with `_timeout_task=None` — verifies no AttributeError, no crash
- Unit: exception raised inside `_loop()` (e.g. from `trigger()`) is caught, logged as `cycle_error`, and the loop continues to the next iteration without crashing
- CSO unit: `cycle.start` received while `_current_cycle_id` is already set — verifies warning is logged and `_run_market_research()` is NOT called (duplicate ignored)
- Integration: `POST /cycles/trigger` → 200 `{"started": true}`
- Integration: second `POST /cycles/trigger` while running → `{"started": false, "reason": "cycle already running"}`
- Integration: `POST /cycles/trigger` when scheduler not initialized (`get_scheduler()` returns None) → `{"started": false, "reason": "scheduler not initialized"}`
- CSO unit: `cycle.start` event triggers `_run_market_research()`
- CSO unit: after cycle completes, `cycle.completed` is published with correct `cycle_id`
