import API from "./client";

export type SignalPayload = {
  strategy_name: string;
  symbol: string;
  capital: number;
  risk_pct: number;
  rr_ratio?: number;
  include_diagnostics?: boolean;
  candles: Array<{
    timestamp?: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume?: number;
  }>;
};

export const api = {
  login: (payload: { username: string; password: string }) =>
    API.post("/auth/login", payload).then((res) => res.data),
  createUser: (payload: { username: string; password: string; role: string }) =>
    API.post("/auth/users", payload).then((res) => res.data),
  health: () => API.get("/health").then((res) => res.data),
  getSummary: () => API.get("/dashboard/summary").then((res) => res.data),
  getStrategies: () => API.get("/trading/strategies").then((res) => res.data),
  strategies: () => API.get("/trading/strategies").then((res) => res.data),
  candles: (symbol: string, interval = "5m") =>
    API.get(`/market/candles/${symbol}`, { params: { interval } }).then((res) => res.data),
  storedCandles: (symbol: string, interval = "1m", limit = 100) =>
    API.get(`/market/stored/${symbol}`, { params: { interval, limit } }).then((res) => res.data),
  marketStoreStatus: (symbol = "NIFTY", interval = "1m") =>
    API.get("/market/store/status", { params: { symbol, interval } }).then((res) => res.data),
  getPrice: () => API.get("/market/price").then((res) => res.data),
  runSignals: (payload: SignalPayload) =>
    API.post("/trading/signals", payload).then((res) => res.data),
  executeOrder: (payload: unknown) =>
    API.post("/execution/order", payload).then((res) => res.data),
  execution: (payload: unknown) =>
    API.post("/execution/order", payload).then((res) => res.data),
  runAnalysis: (payload: unknown) =>
    API.post("/dashboard/live-analysis/jobs", payload).then((res) => res.data),
  getJobs: () => API.get("/dashboard/live-analysis/jobs").then((res) => res.data),
  jobs: () => API.get("/dashboard/live-analysis/jobs").then((res) => res.data),
};
