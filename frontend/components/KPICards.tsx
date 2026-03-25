"use client";
interface CardProps { label: string; value: string; color: string; }
function Card({ label, value, color }: CardProps) {
  return (
    <div className="bg-gray-800 rounded-lg p-6 border border-gray-700">
      <p className="text-gray-400 text-base mb-2">{label}</p>
      <p className={`text-[34px] font-bold ${color}`}>{value}</p>
    </div>
  );
}
interface Props { weeklyRevenue: number; activeCustomers: number; tasksInProgress: number; }
export function KPICards({ weeklyRevenue, activeCustomers, tasksInProgress }: Props) {
  return (
    <div className="grid grid-cols-3 gap-4">
      <Card label="Weekly Revenue" value={`$${weeklyRevenue.toLocaleString()}`} color="text-green-400" />
      <Card label="Active Customers" value={activeCustomers.toLocaleString()} color="text-blue-400" />
      <Card label="Tasks In Progress" value={tasksInProgress.toString()} color="text-yellow-400" />
    </div>
  );
}
