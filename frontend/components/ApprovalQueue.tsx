"use client";
import type { Decision } from "@/types";
interface Props { decisions: Decision[]; onApprove: (id: string) => void; onReject: (id: string) => void; }
export function ApprovalQueue({ decisions, onApprove, onReject }: Props) {
  return (
    <div className="bg-gray-800 rounded-lg border border-gray-700 p-4 h-full">
      <h2 className="text-white font-bold text-base mb-4">APPROVAL QUEUE ({decisions.length})</h2>
      <div className="space-y-3 overflow-y-auto max-h-[600px]">
        {decisions.length === 0 && <p className="text-gray-500 text-sm">No pending decisions</p>}
        {decisions.map((d) => (
          <div key={d.id} className="bg-gray-900 rounded p-3 border border-gray-600">
            <p className="text-white text-sm font-semibold mb-1">{d.title}</p>
            <p className="text-gray-400 text-xs mb-3">{d.description}</p>
            <p className="text-gray-500 text-xs mb-3">Requested by: {d.requested_by.toUpperCase()}</p>
            <div className="flex gap-2">
              <button onClick={() => onApprove(d.id)} className="flex-1 bg-green-600 hover:bg-green-500 text-white text-xs py-1.5 rounded font-semibold">APPROVE</button>
              <button onClick={() => onReject(d.id)} className="flex-1 bg-red-700 hover:bg-red-600 text-white text-xs py-1.5 rounded font-semibold">REJECT</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
