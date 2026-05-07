const BASE = "http://localhost:8000/dashboard";

export const api = {
  summary: () => fetch(`${BASE}/summary`).then(r => r.json()),

  candles: (symbol: string) =>
    fetch(`${BASE}/candles?symbol=${symbol}`).then(r => r.json()),

  jobs: () =>
    fetch(`${BASE}/live-analysis/jobs`).then(r => r.json()),

  job: (id: string) =>
    fetch(`${BASE}/live-analysis/jobs/${id}`).then(r => r.json()),

  runAnalysis: (payload: any) =>
    fetch(`${BASE}/live-analysis`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(r => r.json()),
};