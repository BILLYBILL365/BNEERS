"use client";
import type { Agent } from "@/types";
const STATUS_COLORS: Record<string, string> = {
  active: "bg-green-500",
  thinking: "bg-yellow-400",
  idle: "bg-gray-600",
};
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
