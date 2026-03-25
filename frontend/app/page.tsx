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
    try {
      const [a, t, d] = await Promise.all([
        api.agents.status(),
        api.tasks.list(),
        api.decisions.list("pending"),
      ]);
      setAgents(a);
      setTasks(t);
      setDecisions(d);
    } catch {
      // Backend not yet available — silent fail, will retry on next event
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  useWebSocket(useCallback((event: BusEvent) => {
    if (["task.created", "task.completed", "decision.pending", "agent.status"].includes(event.type)) {
      refresh();
    }
  }, [refresh]));

  const handleApprove = async (id: string) => {
    try {
      await api.decisions.approve(id);
      await refresh();
    } catch (err) {
      console.error("Failed to approve decision:", err);
    }
  };

  const handleReject = async (id: string) => {
    try {
      await api.decisions.reject(id);
      await refresh();
    } catch (err) {
      console.error("Failed to reject decision:", err);
    }
  };

  const activeAgents = agents.filter((a) => a.status === "active").length;
  const weeklyRevenue = 0;
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
