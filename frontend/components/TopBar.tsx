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
