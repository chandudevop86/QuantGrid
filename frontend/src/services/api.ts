const BASE_URL = "http://13.222.179.171:8000";

export const api = {
  health: () => fetch(`${BASE_URL}/health`).then(r => r.json()),

  dashboard: () => fetch(`${BASE_URL}/dashboard`).then(r => r.json()),

  strategies: () => fetch(`${BASE_URL}/trading/strategies`).then(r => r.json()),

  runSignals: (payload: any) =>
    fetch(`${BASE_URL}/trading/signals`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(r => r.json()),

  execution: (payload: any) =>
    fetch(`${BASE_URL}/execution`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(r => r.json()),
};