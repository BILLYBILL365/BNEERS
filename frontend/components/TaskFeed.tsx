"use client";
import type { Task } from "@/types";
const STATUS_STYLES: Record<string, string> = {
  done: "text-green-400",
  in_progress: "text-yellow-400",
  pending: "text-gray-400",
  failed: "text-red-400",
};
interface Props { tasks: Task[]; }
export function TaskFeed({ tasks }: Props) {
  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-4">
      <h2 className="text-white font-bold text-base mb-4">LIVE TASK FEED</h2>
      <div className="space-y-2 max-h-64 overflow-y-auto">
        {tasks.map((t) => (
          <div key={t.id} className="flex items-center justify-between text-sm">
            <span className="text-gray-300 truncate max-w-[60%]">{t.title}</span>
            <div className="flex items-center gap-3">
              <span className="text-gray-500 text-xs">{t.agent_id.toUpperCase()}</span>
              <span className={`text-xs font-semibold uppercase ${STATUS_STYLES[t.status]}`}>{t.status}</span>
            </div>
          </div>
        ))}
        {tasks.length === 0 && <p className="text-gray-500 text-sm">No tasks yet</p>}
      </div>
    </div>
  );
}
