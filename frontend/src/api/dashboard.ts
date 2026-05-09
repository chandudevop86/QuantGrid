import API from "../services/api";

export const api = {
  summary: () => API.get("/dashboard/summary").then(r => r.data),

  candles: (symbol: string) =>
    API.get(`/dashboard/candles?symbol=${symbol}`).then(r => r.data),

  jobs: () =>
    API.get("/dashboard/live-analysis/jobs").then(r => r.data),

  job: (id: string) =>
    API.get(`/dashboard/live-analysis/jobs/${id}`).then(r => r.data),

  runAnalysis: (payload: any) =>
    API.post("/dashboard/live-analysis", payload).then(r => r.data),
};
useLive((data) => {
  console.log("LIVE:", data);
});