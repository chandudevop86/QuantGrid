import API from "./client";

export const api = {
  health: () => API.get("/health").then((res) => res.data),
  getSummary: () => API.get("/dashboard/summary").then((res) => res.data),
  getStrategies: () => API.get("/trading/strategies").then((res) => res.data),
  runSignals: (payload: any) => API.post("/trading/signals", payload).then((res) => res.data),
  executeTrade: (payload: any) => API.post("/execution", payload).then((res) => res.data),
  executeOrder: (payload: any) => API.post("/execution", payload).then((res) => res.data),
  runAnalysis: (payload: any) => API.post("/dashboard/live-analysis/jobs", payload).then((res) => res.data),
  getJobs: () => API.get("/dashboard/live-analysis/jobs").then((res) => res.data),
};
