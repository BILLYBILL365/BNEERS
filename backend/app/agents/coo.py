from __future__ import annotations

from app.agents.base import BaseAgent
from app.schemas.events import BusEvent


class COO(BaseAgent):
    """Chief Operating Officer — task coordination, deadlock detection and resolution.

    Phase 3: maintains a task dependency graph. On each new task.created, runs cycle
    detection via DFS. On cycle → escalates to Board immediately.
    """

    agent_id = "coo"

    def __init__(self, bus, audit) -> None:
        super().__init__(bus=bus, audit=audit)
        # task_id → {"depends_on": set[str], "task_type": str}
        self._task_graph: dict[str, dict] = {}

    async def on_start(self) -> None:
        await self.subscribe("task.created", self._on_task_created)
        await self.subscribe("task.completed", self._on_task_completed)
        await self.subscribe("agent.escalation", self._on_escalation)
        await self._audit.log(agent_id=self.agent_id, event_type="agent_started", payload={})

    async def _on_task_created(self, event: BusEvent) -> None:
        task_id = event.payload.get("task_id")
        depends_on = set(event.payload.get("depends_on", []))
        task_type = event.payload.get("task_type", "unknown")

        if task_id:
            self._task_graph[task_id] = {
                "depends_on": depends_on,
                "task_type": task_type,
            }
            cycle = self._find_cycle()
            if cycle:
                await self._audit.log(
                    agent_id=self.agent_id,
                    event_type="deadlock_detected",
                    payload={"cycle": cycle},
                    outcome="escalated",
                )
                await self._escalate(
                    reason=f"Deadlock detected in task graph: {' → '.join(cycle)}",
                    context={"cycle": cycle},
                )
                return

        await self._audit.log(
            agent_id=self.agent_id,
            event_type="task.created",
            payload=event.payload,
            outcome="acknowledged",
        )

    async def _on_task_completed(self, event: BusEvent) -> None:
        task_id = event.payload.get("task_id")
        if task_id and task_id in self._task_graph:
            del self._task_graph[task_id]
        await self._audit.log(
            agent_id=self.agent_id,
            event_type="task.completed",
            payload=event.payload,
            outcome="acknowledged",
        )

    async def _on_escalation(self, event: BusEvent) -> None:
        await self._audit.log(
            agent_id=self.agent_id,
            event_type="escalation_received",
            payload=event.payload,
            outcome="acknowledged",
        )

    def _find_cycle(self) -> list[str] | None:
        """DFS cycle detection. Returns cycle path if found, else None."""
        visited: set[str] = set()
        path: set[str] = set()

        def dfs(node: str, trail: list[str]) -> list[str] | None:
            if node in path:
                idx = trail.index(node)
                return trail[idx:] + [node]
            if node in visited:
                return None
            visited.add(node)
            path.add(node)
            for dep in self._task_graph.get(node, {}).get("depends_on", set()):
                result = dfs(dep, trail + [dep])
                if result:
                    return result
            path.discard(node)
            return None

        for task_id in list(self._task_graph.keys()):
            result = dfs(task_id, [task_id])
            if result:
                return result
        return None
