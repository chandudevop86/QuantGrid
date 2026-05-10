const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request(path: string, options?: RequestInit) {
  const response = await fetch(`${BASE_URL}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(options?.headers ?? {}) },
    ...options,
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  return response.json();
}

export const api = {
  health: () => request("/health"),
  dashboard: () => request("/dashboard"),
  getSummary: () => request("/dashboard/summary"),
  strategies: () => request("/trading/strategies"),
  runSignals: (payload: any) =>
    request("/trading/signals", { method: "POST", body: JSON.stringify(payload) }),
  execution: (payload: any) =>
    request("/execution", { method: "POST", body: JSON.stringify(payload) }),
  runAnalysis: (payload: any) =>
    request("/dashboard/live-analysis/jobs", { method: "POST", body: JSON.stringify(payload) }),
  getJobs: () => request("/dashboard/live-analysis/jobs"),
};
