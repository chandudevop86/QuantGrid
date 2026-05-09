import API from "./client";

export const api = {
  // Health
  health: () => API.get("/health").then(res => res.data),

  // Dashboard
  getSummary: () =>
    API.get("/dashboard/summary").then(res => res.data),

  // Strategies
  getStrategies: () =>
    API.get("/trading/strategies").then(res => res.data),

  // Run signals
  runSignals: (payload: any) =>
    API.post("/trading/signals", payload).then(res => res.data),

  // Execution
  executeTrade: (payload: any) =>
    API.post("/execution", payload).then(res => res.data),

  // Live analysis
  runAnalysis: (data: any) =>
    API.post("/dashboard/live-analysis/jobs", data).then(res => res.data),

  getJobs: () =>
    API.get("/dashboard/live-analysis/jobs").then(res => res.data),
};


