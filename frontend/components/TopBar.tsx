"use client";

interface Props {
  agentCount: number;
  weeklyRevenue: number;
  pendingApprovals: number;
  onStartCycle: () => void;
  cycleStatus: string | null;
  cycleLoading: boolean;
}

export function TopBar({
  agentCount,
  weeklyRevenue,
  pendingApprovals,
  onStartCycle,
  cycleStatus,
  cycleLoading,
}: Props) {
  return (
    <div className="flex items-center justify-between bg-gray-900 border-b border-gray-700 px-6 py-3">
      <h1 className="text-xl font-bold text-white tracking-wide">
        PROJECT MILLION — MISSION CONTROL
      </h1>
      <div className="flex items-center gap-6 text-sm">
        <span className="text-green-400 font-semibold">{agentCount} AGENTS LIVE</span>
        <span className="text-yellow-400 font-semibold">
          ${weeklyRevenue.toLocaleString()} / WEEK
        </span>
        <span className="text-red-400 font-semibold">{pendingApprovals} PENDING</span>
        <button
          onClick={onStartCycle}
          disabled={cycleLoading}
          className="px-3 py-1 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-600 text-white text-sm font-semibold rounded transition-colors"
        >
          {cycleLoading ? "Starting..." : "▶ Start Cycle"}
        </button>
        {cycleStatus && (
          <span className="text-blue-300 text-xs font-medium">{cycleStatus}</span>
        )}
      </div>
    </div>
  );
}
