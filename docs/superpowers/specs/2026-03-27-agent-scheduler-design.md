# Agent Scheduler Design

**Date:** 2026-03-27
**Status:** Approved

---

## Goal

Automatically run a full lead generation and outreach cycle every 6 hours (configurable) for **Lead Supremacy AI** — the user's existing GHL SaaS business targeting local service businesses. Allow the Board to manually trigger a cycle from Mission Control. One cycle runs at a time.

One **business cycle** = CSO finds and scores leads → Board approves lead list → CMO drafts outreach emails → Board approves outreach → CMO sends emails. The cycle completes when outreach is sent, or when the Board rejects at any gate.

---

## Architecture

A single new component — `AgentScheduler` — runs inside the existing FastAPI/uvicorn process as an asyncio background task, alongside the `AgentRunner` and Redis bus loop already started in `main.py`.

```
main.py lifespan
├── AgentRunner          (existing — owns C-Suite agents: CSO, CMO, COO, CFO)
├── AgentScheduler       (new — owns schedule loop + cycle state)
└── RedisBus loop        (existing — event pump)
```

The scheduler communicates with agents exclusively through the Redis bus. It publishes `cycle.start` (with a `cycle_id`) to begin a cycle. The last agent to finish a cycle (CMO, or CSO if rejected at gate 1) publishes `cycle.completed`. The scheduler subscribes to `cycle.completed` to know when a cycle has resolved.

**`cycle_id` threading:** `cycle_id` is stored on the `Decision` model (new optional field). The router includes it in `decision.approved`/`decision.rejected` events when present. This allows CSO and CMO to identify which decision ends their cycle step without fragile in-memory `_pending_decision_id` tracking.

---

## Cycle Flow

### Automatic (scheduled)
1. `AgentScheduler._loop()` sleeps for `CYCLE_INTERVAL_SECONDS`, **then** calls `trigger()`. The first cycle fires after the first full interval — not immediately on startup. This is intentional: startup may still be settling, and manual trigger is available for immediate execution.
2. Calls `trigger()` — skips if `_cycle_running` is True
3. Sets `_cycle_running = True`, generates a `cycle_id` (UUID4), stores as `_current_cycle_id`
4. Publishes `cycle.start` with `{"cycle_id": "<uuid>"}` on the bus

**Gate 1 — CSO lead research:**

5. CSO's `_on_cycle_start()` stores `cycle_id`, calls `_run_lead_research()`
6. `_run_lead_research()` scrapes Google Ads Transparency Center, scores leads, builds top 10–15 list
7. CSO posts `decision.pending` (title: "Lead list ready", lead data in description, `cycle_id` in extra_payload → stored on Decision record)
8a. Board rejects → `decision.rejected {decision_id, cycle_id}` → CSO publishes `cycle.completed {cycle_id, outcome: "rejected"}` → **cycle ends**
8b. Board approves → `decision.approved {decision_id, cycle_id}` → CSO publishes `leads.approved {cycle_id, leads: [...]}` → CMO picks up

**Gate 2 — CMO outreach:**

9. CMO's `_on_leads_approved()` receives leads and `cycle_id`
10. CMO drafts personalized cold emails for each approved lead (LLM-generated)
11. CMO posts `decision.pending` (title: "Outreach drafts ready", drafts in description, `cycle_id` in extra_payload)
12a. Board rejects → `decision.rejected {decision_id, cycle_id}` → CMO publishes `cycle.completed {cycle_id, outcome: "rejected"}` → **cycle ends**
12b. Board approves → `decision.approved {decision_id, cycle_id}` → CMO sends emails → CMO publishes `cycle.completed {cycle_id, outcome: "sent"}` → **cycle ends**

**Scheduler cleanup:**

13. `AgentScheduler._on_cycle_completed()` checks `cycle_id` matches `_current_cycle_id`, resets `_cycle_running = False`, cancels the timeout task

### Manual (Board-initiated)
- `POST /cycles/trigger` calls `AgentScheduler.trigger()` directly
- Returns `{"started": true}` if cycle began
- Returns `{"started": false, "reason": "cycle already running"}` if skipped (HTTP 200 — not an error)

### Skip path
`trigger()` checks `_cycle_running` before doing anything. If True: logs `cycle_skipped` to audit, returns False.

### Timeout / safety reset
When a cycle starts, a 4-hour `asyncio.Task` (`_timeout_task`) is created. If it fires before `_on_cycle_completed()`:
- Guards with `if not self._cycle_running: return`
- Resets `_cycle_running = False`, `_current_cycle_id = None`
- Clears `_timeout_task` to `None`
- Publishes `agent.alert` on the bus (Discord alert fires via King Solomon — payload: `{"agent_id": "scheduler", "reason": "cycle_timeout", "message": "Cycle timed out after 4 hours"}`)
- Logs `cycle_timeout` to audit

`_on_cycle_completed()` always cancels `_timeout_task` when it fires — before any `await` — so the timeout never fires on a resolved cycle. Guard with `if self._timeout_task and not self._timeout_task.done()` before cancelling.

**Race condition handling:** Both `_on_cycle_completed()` and `_on_timeout()` must begin with `if not self._cycle_running: return`. Because asyncio is single-threaded and task cancellation is only checked at `await` points, calling `self._timeout_task.cancel()` synchronously (before any `await`) inside `_on_cycle_completed()` prevents `_on_timeout` from advancing past its next `await`. The guard at the top of both handlers ensures only the first one resets state.

### Error handling
Any exception inside `_loop()` is caught with `except Exception` (not `BaseException` — `CancelledError` must propagate so `stop()` can cancel the task), logged as `cycle_error` to audit, and the loop resumes after the next interval. The loop never crashes the process.

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
    async def start(self) -> None        # registers subscriptions (cycle.completed), begins _loop_task
    async def stop(self) -> None         # cancels _loop_task and _timeout_task; awaits cancellation; swallows CancelledError
    async def trigger(self) -> bool      # True=started (sets _cycle_running, stores _current_cycle_id, publishes cycle.start, logs cycle_started), False=skipped (logs cycle_skipped)
    async def _loop(self) -> None        # sleep(interval) → trigger() → repeat; catches Exception (not BaseException); logs cycle_error
    async def _on_cycle_completed(self, event: BusEvent) -> None  # guard: if not _cycle_running: return; validate cycle_id matches; reset state; cancel timeout
    async def _on_timeout(self) -> None  # await asyncio.sleep(4h); guard: if not _cycle_running: return; reset _cycle_running=False, _current_cycle_id=None, _timeout_task=None; publish agent.alert; log cycle_timeout
```

`_timeout_task` is created as `asyncio.create_task(self._on_timeout())` — `_on_timeout` is the task coroutine itself. It does `await asyncio.sleep(4 * 3600)` internally, then performs cleanup if not cancelled.

`trigger()` is `async` because it `await`s the bus publish. All call sites must `await` it.

`BusEvent` is imported from `app.schemas.events`.

`start()` registers subscriptions internally — consistent with how `AgentRunner` and `DiscordNotifier` register in their own `start()` methods.

`stop()` must `await` cancellation of both tasks and swallow `asyncio.CancelledError`. The scheduler is stopped **before** the bus loop is cancelled (see Shutdown Order), so any in-flight `agent.alert` from a mid-cancellation timeout may still publish successfully — this is acceptable.

---

**`backend/app/routers/cycles.py`**
- `POST /cycles/trigger` endpoint
- Calls `await get_scheduler().trigger()`
- Returns `CycleTriggerResponse(started: bool, reason: str | None = None)`
- If scheduler is not initialized, returns `{"started": false, "reason": "scheduler not initialized"}`

---

### Modified files

**`backend/app/models/decision.py`**
- Add `cycle_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)` — stores the scheduler cycle this decision belongs to; `None` for decisions not triggered by the scheduler
- Alembic migration required: `alembic revision --autogenerate -m "add cycle_id to decisions"`

**`backend/app/routers/decisions.py`**
- In `approve_decision()`: read `decision.cycle_id`; if not None, include `"cycle_id": decision.cycle_id` in the `decision.approved` event payload
- In `reject_decision()`: same — include `"cycle_id": decision.cycle_id` if not None

**`backend/app/agents/base.py`**
- `request_decision()` already accepts `extra_payload` — no change to signature
- The `cycle_id` value is passed via `extra_payload={"cycle_id": ..., ...}` by the caller; it is then stored in the Decision DB record automatically through the `decision.pending` event handler in `decisions.py` — **but `decisions.py`'s `_on_pending` handler must be updated** to extract `cycle_id` from the payload and set it on the Decision record before saving

**`backend/app/services/decisions.py`**
- In `_on_pending()`: extract `cycle_id = payload.get("cycle_id")`; set `decision.cycle_id = cycle_id` before `db.commit()`

---

**`backend/app/agents/cso.py`**

CSO is redesigned for lead prospecting. The old "market research → approve_opportunity" pipeline is replaced.

New instance attributes:
- `_current_cycle_id: str | None = None`

Changes:
- In `on_start()`: replace `decision.approved`/`decision.rejected` subscriptions with `cycle.start` subscription: `await self.subscribe("cycle.start", self._on_cycle_start)`
- Add `_on_cycle_start(event)` handler:
  1. Guard: `if self._current_cycle_id is not None: log warning, return`
  2. Store `self._current_cycle_id = event.payload["cycle_id"]`
  3. Call `await self._run_lead_research()`
- Replace `_run_market_research()` with `_run_lead_research()`:
  1. Scrape Google Ads Transparency Center for local service businesses (using browser automation or API)
  2. Score leads by relevance, ad spend signals, and niche fit
  3. Build top 10–15 scored lead list
  4. Call `request_decision(title="Lead list ready: N prospects", description=<formatted list>, extra_payload={"task": "approve_leads", "cycle_id": self._current_cycle_id, "leads": [...]})`
- Add `_on_decision_approved(event)` handler:
  - If `event.payload.get("cycle_id") == self._current_cycle_id`: publish `leads.approved {cycle_id, leads: event.payload["leads"]}`, clear `_current_cycle_id`
  - Else: log acknowledged (non-cycle decision, ignore)
- Add `_on_decision_rejected(event)` handler:
  - If `event.payload.get("cycle_id") == self._current_cycle_id`: publish `cycle.completed {cycle_id: self._current_cycle_id, outcome: "rejected"}`, clear `_current_cycle_id`
  - Else: log acknowledged

**Note:** Old subscriptions (`decision.approved`, `decision.rejected`) are removed from CSO — CSO now only subscribes to `cycle.start`. The `cycle_id` check on approved/rejected events provides the matching guard; no `_pending_decision_id` needed since `cycle_id` is now in the event payload directly.

---

**`backend/app/agents/cmo.py`**

CMO gains a cycle-aware pipeline for outreach drafting and sending.

New instance attributes:
- `_current_cycle_id: str | None = None`

Changes:
- In `on_start()`: add `await self.subscribe("leads.approved", self._on_leads_approved)`
- Add `_on_leads_approved(event)` handler:
  1. Guard: `if self._current_cycle_id is not None: log warning, return`
  2. Store `self._current_cycle_id = event.payload["cycle_id"]`
  3. Call `await self._draft_outreach(event.payload["leads"])`
- Add `_draft_outreach(leads)`:
  1. For each lead: generate a personalized cold email using LLM (subject + body referencing their business, Google Ads spend, and Lead Supremacy AI offer)
  2. Call `request_decision(title="Outreach drafts ready: N emails", description=<formatted drafts>, extra_payload={"task": "approve_outreach", "cycle_id": self._current_cycle_id, "drafts": [...]})`
- Add `_on_decision_approved(event)` handler:
  - If `event.payload.get("cycle_id") == self._current_cycle_id`: call `await self._send_outreach(event.payload["drafts"])`, then publish `cycle.completed {cycle_id, outcome: "sent"}`, clear `_current_cycle_id`
  - Else: log acknowledged
- Add `_on_decision_rejected(event)` handler:
  - If `event.payload.get("cycle_id") == self._current_cycle_id`: publish `cycle.completed {cycle_id, outcome: "rejected"}`, clear `_current_cycle_id`
  - Else: log acknowledged
- Add `_send_outreach(drafts)`: sends emails via configured email provider (stubbed initially — logs each send to audit as `email_sent`, actual SMTP/API integration is a follow-on task)

---

**`backend/app/main.py`**
- Add `from app.scheduler import AgentScheduler, set_scheduler`
- Add `from app.routers import cycles` and `app.include_router(cycles.router)`
- After `runner.start()`: instantiate `AgentScheduler`, call `set_scheduler(scheduler)`, call `await scheduler.start()`
- Shutdown order: stop scheduler **before** cancelling `bus_task`
- Remove CTO from `AgentRunner` if present — active agents are CSO, CMO, COO, CFO only

**`backend/app/config.py`**
- Add `CYCLE_INTERVAL_SECONDS: int = 21600`

**`.env.example`** and **`.env.production.example`**
- Add `CYCLE_INTERVAL_SECONDS=21600`

**`frontend/lib/api.ts`**
- Add `cycles: { trigger: () => post<{ started: boolean; reason?: string }>("/cycles/trigger") }`

**`frontend/app/page.tsx`**
- Add "▶ Start Cycle" button in the top bar area
- On click: disable button and show loading indicator while awaiting response
- After response: re-enable button, show inline status for 3 seconds:
  - `response.started === true` → display `"Cycle started"`
  - `response.started === false` → display `response.reason` from API
- Button is NOT kept disabled for the duration of the cycle — if clicked again while running, API returns `{"started": false, "reason": "cycle already running"}` which is displayed

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
| `cycle.start` | AgentScheduler | `{"cycle_id": "<uuid>"}` | New cycle beginning — CSO should run lead research |
| `leads.approved` | CSO | `{"cycle_id": "<uuid>", "leads": [{name, score, niche, google_ads_url, ...}]}` | Board approved lead list — CMO should draft outreach |
| `cycle.completed` | CSO or CMO | `{"cycle_id": "<uuid>", "outcome": "sent"\|"rejected"}` | Cycle finished — scheduler resets state |
| `agent.alert` | AgentScheduler | `{"agent_id": "scheduler", "reason": "cycle_timeout", "message": "Cycle timed out after 4 hours"}` | Cycle timed out |

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

Scheduler is stopped first to prevent new `cycle.start` publications after the bus loop is cancelled. The bus is still live during `scheduler.stop()`, so any in-flight `agent.alert` from a mid-cancellation timeout may still publish — this is acceptable.

---

## Testing

**Scheduler unit:**
- `trigger()` returns False, logs `cycle_skipped` when `_cycle_running=True`
- `trigger()` returns True, sets `_cycle_running=True`, publishes `cycle.start`, logs `cycle_started` when idle
- `_on_cycle_completed()` resets `_cycle_running`, cancels timeout task
- `_on_cycle_completed()` ignores events with non-matching `cycle_id`
- `_on_cycle_completed()` called while `_timeout_task` pending — verifies timeout is cancelled and does not subsequently reset `_cycle_running`
- `_on_cycle_completed()` called with `_timeout_task=None` — no crash
- `_on_timeout()` resets flag, clears `_current_cycle_id`, publishes `agent.alert`, logs `cycle_timeout`
- Exception in `_loop()` is caught, logged as `cycle_error`, loop continues

**CSO unit:**
- `cycle.start` triggers `_run_lead_research()`
- `cycle.start` while `_current_cycle_id` is already set — warning logged, `_run_lead_research()` NOT called
- `decision.approved` with matching `cycle_id` → publishes `leads.approved`, clears `_current_cycle_id`
- `decision.approved` with non-matching `cycle_id` → no `leads.approved`, no state change
- `decision.rejected` with matching `cycle_id` → publishes `cycle.completed {outcome: "rejected"}`, clears `_current_cycle_id`
- `decision.rejected` with non-matching `cycle_id` → no `cycle.completed`, cycle remains active

**CMO unit:**
- `leads.approved` triggers `_draft_outreach()`
- `leads.approved` while `_current_cycle_id` is already set — warning logged, draft NOT called
- `decision.approved` with matching `cycle_id` → calls `_send_outreach()`, publishes `cycle.completed {outcome: "sent"}`
- `decision.rejected` with matching `cycle_id` → publishes `cycle.completed {outcome: "rejected"}`

**Integration:**
- `POST /cycles/trigger` → 200 `{"started": true}`
- Second `POST /cycles/trigger` while running → `{"started": false, "reason": "cycle already running"}`
- `POST /cycles/trigger` when scheduler not initialized → `{"started": false, "reason": "scheduler not initialized"}`

**Decision model:**
- `cycle_id` is persisted on Decision record when passed in `extra_payload`
- `decision.approved` event includes `cycle_id` when set on Decision record
- `decision.rejected` event includes `cycle_id` when set on Decision record
