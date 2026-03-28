const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return res.json();
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`);
  return res.json();
}

export const api = {
  decisions: {
    list: (status?: string) =>
      get<import("@/types").Decision[]>(`/decisions${status ? `?status=${status}` : ""}`),
    approve: (id: string) => post<import("@/types").Decision>(`/decisions/${id}/approve`),
    reject: (id: string) => post<import("@/types").Decision>(`/decisions/${id}/reject`),
  },
  tasks: {
    list: () => get<import("@/types").Task[]>("/tasks"),
  },
  agents: {
    status: () => get<import("@/types").Agent[]>("/agents/status"),
  },
  cycles: {
    trigger: () => post<{ started: boolean; reason?: string }>("/cycles/trigger"),
  },
};
