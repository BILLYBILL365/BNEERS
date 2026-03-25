# Project Million — Design Document

**Goal:** An autonomous multi-agent system that identifies a SaaS market opportunity, builds the product, sells it, and grows it — targeting $1M/week revenue.

**Role of the user:** Board-level oversight. Approves major decisions. Agents handle everything else.

---

## Table of Contents

1. [Architecture](#1-architecture)
2. [Mission Control Dashboard](#2-mission-control-dashboard)
3. [Agent Communication & Data Flow](#3-agent-communication--data-flow)
4. [Error Handling, Escalation & Audit Trail](#4-error-handling-escalation--audit-trail)
5. [Testing Strategy](#5-testing-strategy)
6. [Tech Stack](#6-tech-stack)

---

## 1. Architecture

### Approach: Hierarchical Multi-Agent Teams

The system is organized as a company. C-Suite agents own strategy and coordination. Worker agents execute specific tasks under each C-Suite agent.

### C-Suite Agents

| Agent | Role |
|---|---|
| CSO (Strategy) | Market research, opportunity identification, product direction |
| CTO (Product) | Builds and ships the SaaS, manages code agents |
| CMO (Marketing) | Content, ads, SEO, social media, email campaigns |
| CFO (Finance) | Revenue tracking, cost optimization, pricing |
| COO (Operations) | Customer support, task coordination, dependency resolution |

### Worker Agents

| C-Suite | Workers |
|---|---|
| CSO | Market Scanner, Opportunity Evaluator |
| CTO | Code Writer, QA Tester, DevOps |
| CMO | Content Writer, Social Media Agent, Email Campaign Agent, Ad Manager |
| CFO | Revenue Tracker, Pricing Optimizer |
| COO | Support Agent, Task Coordinator |

### Hierarchy Diagram

```
                    ┌──────────────┐
                    │  BOARD (You) │
                    └──────┬───────┘
           ┌───────┬───────┼───────┬───────┐
         CSO      CTO     CMO     CFO     COO
          │        │       │       │       │
       Workers  Workers Workers Workers Workers
```

---

## 2. Mission Control Dashboard

### Layout

- **Top bar:** live agent count, weekly revenue, pending approvals count
- **KPI cards:** Weekly Revenue, Active Customers, Tasks In Progress
- **Approval queue** (right column, always visible): one-click approve/reject per pending decision
- **Agent status grid:** all agents color-coded (green=active, yellow=thinking, grey=idle)
- **Live task feed:** done / in progress / pending tasks with agent attribution

### Design Specs

- Base font: 16px
- KPI values: 34px
- Web app, mobile-friendly
- Real-time updates via WebSockets
- Reference mockup: `mission-control-v3.html`

---

## 3. Agent Communication & Data Flow

### Message Bus

All agent communication flows through a central **Redis pub/sub message bus**. No agent communicates directly with another. This keeps the system auditable and failure-isolated.

```
[Agent] → publishes event → [Redis Bus] → subscribes → [Agent / Dashboard]
```

### Event Types

| Event | Published By | Consumed By |
|---|---|---|
| `task.created` | Any C-Suite | COO, Dashboard |
| `task.completed` | Any Worker | Parent C-Suite, Dashboard |
| `decision.pending` | Any C-Suite | Board, Audit Log |
| `decision.approved` | Board | Triggering C-Suite |
| `decision.rejected` | Board | Triggering C-Suite + CSO |
| `revenue.updated` | CFO | Dashboard, All C-Suite |
| `agent.status` | Any Agent | Dashboard |

### Decision Flow (Human-in-the-Loop)

```
Agent hits a threshold decision
        ↓
Posts to decision.pending queue
        ↓
Dashboard surfaces it in Approval Queue
        ↓
Board approves or rejects (one click)
        ↓
Agent receives result and continues
        ↓
Full decision logged to audit trail
```

**Decision thresholds (configurable):**
- Spending > $X on ads
- Launching a new product
- Pivoting market strategy
- Spawning / retiring a worker agent
- Major code deployment to production

### Task Delegation Flow

```
CSO identifies opportunity
    ↓
Posts task.created → CTO + CMO
    ↓
CTO spawns: Code Writer → QA → DevOps
CMO spawns: Content Writer → Ad Manager
    ↓
Each worker reports task.completed
    ↓
C-Suite aggregates and reports up
    ↓
COO tracks overall progress
```

### Full Data Flow

```
                    ┌─────────────┐
                    │  BOARD (You) │
                    └──────┬──────┘
                           │ approve/reject
                    ┌──────▼──────┐
              ┌────►│  REDIS BUS  │◄────┐
              │     └──────┬──────┘     │
              │            │            │
        ┌─────▼──┐   ┌─────▼──┐  ┌─────▼──┐
        │  CSO   │   │  CTO   │  │  CMO   │
        └─────┬──┘   └─────┬──┘  └─────┬──┘
              │             │            │
         [Workers]     [Workers]    [Workers]
              │             │            │
              └─────────────▼────────────┘
                       PostgreSQL
                    (Tasks, Decisions,
                      Audit Log)
```

### Agent Activation Model

Agents are **event-driven** — they wake on messages, not timers.

**Exception:** Market Scanner (under CSO) runs on a configurable scheduled interval to continuously scan for opportunities.

---

## 4. Error Handling, Escalation & Audit Trail

### Retry Policy

| Tier | Max Retries | Backoff | On Final Failure |
|---|---|---|---|
| Worker Agent | 3 | Exponential (2s → 4s → 8s) | Escalate to C-Suite |
| C-Suite Agent | 2 | 30s flat | Escalate to Board |
| Board | — | — | System pause |

### Human Escalation Triggers

The following always escalate to the Board regardless of retry policy:
- Any C-Suite agent fails after retries
- Revenue drops >20% week-over-week
- Unexpected API cost spike (exceeds daily hard cap)
- Legal/compliance flag detected in generated content
- Two or more agents in deadlock

### Deadlock Prevention

The COO acts as dependency resolver. If a circular task dependency is detected, COO breaks it by prioritizing based on revenue impact.

### Audit Trail

Every action is persisted to PostgreSQL. Nothing is ephemeral.

**Schema:**
```sql
audit_log (
    id            UUID PRIMARY KEY,
    timestamp     TIMESTAMPTZ,
    agent_id      VARCHAR,
    event_type    VARCHAR,   -- task | decision | error | escalation
    payload       JSONB,     -- full context
    decision_by   VARCHAR,   -- agent_id or 'board'
    outcome       VARCHAR    -- success | failed | rejected | escalated
)
```

The audit trail can answer:
- Why did the CSO pick this market?
- What did the CMO spend on ads last week?
- Which agent caused the revenue dip on a given date?
- What decisions did the Board approve in the last 30 days?

### System Health Monitor

A lightweight watchdog (cron process, not an AI agent) checks:
- All C-Suite agents heartbeating every 60s
- Redis bus lag < 500ms
- PostgreSQL write queue not backing up

On any failure → immediate Board notification via dashboard alert banner.

### Graceful Degradation

| Agent Down | Impact | System Response |
|---|---|---|
| Ad Manager | Ads paused | CMO notified, no escalation |
| Email Campaign | Emails paused | CMO notified |
| QA Tester | Deploys blocked | CTO escalates to Board |
| CFO | Revenue tracking paused | Board alerted immediately |
| CSO | Strategy frozen | Board alerted immediately |

---

## 5. Testing Strategy

### Environments

| Environment | Purpose | Real Money? | Real APIs? |
|---|---|---|---|
| Local | Dev & unit tests | No | Mocked |
| Staging | Integration & agent behavior | No | Sandbox |
| Production | Live system | Yes | Live |

All production deploys require Board approval via the DevOps agent.

### Test Layers

**Unit Tests**
- Each agent's core logic in isolation
- Mock message bus and external APIs
- Run on every commit
- Coverage target: 80%+ on agent decision logic

**Integration Tests**
- Real Redis + PostgreSQL via Docker Compose
- Test full event flows end-to-end
- Verify audit log correctness
- Run on every PR

**Agent Behavior Tests**
- Staging environment with sandbox APIs
- Scripted scenarios: CSO finds opportunity → CTO builds MVP → CMO launches campaign
- Assert outcomes (did revenue tracker update? did approval queue fire?)
- Run nightly

**Chaos Tests**
- Kill random worker agents mid-task — verify escalation fires
- Simulate Redis lag — verify dashboard still updates
- Inject malformed LLM responses — verify retry/schema validation kicks in
- Run weekly

### Agent Prompt Testing

LLM outputs are non-deterministic. Handled via:
- **Evals** — test suite of known inputs with expected output categories
- **Schema validation** — every agent response parsed against a Pydantic model; malformed output triggers retry
- **Canary prompts** — before any prompt change ships, run 20 sample inputs and check pass rate

### Staging Simulation (Pre-Launch Gate)

Before going live, run a full **48-hour simulation** in staging:
- CSO runs real market research (sandbox)
- CTO scaffolds a real repo (private GitHub)
- CMO drafts real content (not published)
- CFO tracks simulated revenue events
- Board approval queue fires with real decisions

If simulation completes without critical escalations → green light for production.

### Production Monitoring

- Automated regression: integration suite against production read-only endpoints daily
- Revenue anomaly detection: CFO flags statistical outliers automatically
- LLM cost alerts: if agent API spend exceeds budget thresholds, system pauses and alerts Board

---

## 6. Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python + FastAPI |
| Agent Reasoning | Claude Sonnet (complex) |
| Agent Workers | Claude Haiku / GPT-4o (simpler tasks) |
| Frontend | Next.js (web + mobile-friendly) |
| Primary DB | PostgreSQL (tasks, decisions, audit log) |
| Message Bus | Redis (pub/sub) |
| Real-time | WebSockets (dashboard live updates) |
| Local/Staging | Docker Compose |
| Production | Railway (managed PostgreSQL + Redis, GitHub auto-deploy) |

---

---

## 7. Key Decisions & Constraints

### Board Approval Gates (required, not optional)

| Decision | Triggered By |
|---|---|
| SaaS opportunity selection | CSO presents, Board approves before CTO starts |
| Spending above daily cap | Any agent, automatic hold |
| Spending above weekly soft cap | CFO presents, Board approves to continue |
| New product launch | CTO + CMO, Board approves |
| Market pivot | CSO, Board approves |
| Production deployment | DevOps agent, Board approves |

### Spending Guardrails

| Cap Type | Scope | Behavior on Hit |
|---|---|---|
| Daily hard cap | Per agent category (ads, APIs, etc.) | Auto-pause, Board notified |
| Weekly soft cap | Total system spend | Board approval required to exceed |
| Monthly hard ceiling | Total system spend | System pauses until next month or Board override |

### Timeline

Target: production-ready within 30 days.

**Phases:**
- Phase 1 (Days 1–10): Core infrastructure — FastAPI backend, Redis bus, PostgreSQL, WebSocket dashboard shell
- Phase 2 (Days 11–20): Agent framework — C-Suite + Worker agents, decision queue, audit log
- Phase 3 (Days 21–28): Intelligence & automation — CSO market research, CTO code generation, CMO campaigns
- Phase 4 (Days 29–30): Staging simulation, Railway deploy, go-live

---

*Design document complete. Next: implementation planning.*
