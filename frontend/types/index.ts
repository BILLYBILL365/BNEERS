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
  created_at: string;
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

export interface BusEvent {
  id: string;
  type: string;
  payload: Record<string, unknown>;
  timestamp: string;
}

export interface KPIs {
  weekly_revenue: number;
  active_customers: number;
  tasks_in_progress: number;
  pending_approvals: number;
  active_agents: number;
}
