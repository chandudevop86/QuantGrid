import API from "./client";

export type SignalPayload = {
  strategy_name: string;
  symbol: string;
  capital: number;
  risk_pct: number;
  rr_ratio?: number;
  include_diagnostics?: boolean;
  candle_source?: string;
  candles: Array<{
    timestamp?: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume?: number;
  }>;
  htf_candles?: SignalPayload["candles"];
  mtf_candles?: SignalPayload["candles"];
  daily_candles?: SignalPayload["candles"];
};

export const api = {
  login: (payload: { username: string; password: string }) =>
    API.post("/auth/login", payload).then((res) => res.data),
  createUser: (payload: { username: string; password: string; role: string }) =>
    API.post("/admin/users/create", payload).then((res) => res.data),
  listUsers: () => API.get("/admin/users").then((res) => res.data),
  getNotificationStatus: () => API.get("/admin/notifications/status").then((res) => res.data),
  sendTestNotification: () => API.post("/admin/notifications/test").then((res) => res.data),
  resetUserPassword: (userId: number, password: string) =>
    API.post(`/admin/users/${userId}/reset-password`, { password }).then((res) => res.data),
  changeUserPassword: (userId: number, oldPassword: string | null, newPassword: string) =>
    API.post(`/admin/users/${userId}/change-password`, { old_password: oldPassword, new_password: newPassword }).then((res) => res.data),
  deleteUser: (userId: number) => API.delete(`/admin/users/${userId}`).then((res) => res.data),
  health: () =>
    API.get("/api/health")
      .then((res) => res.data)
      .catch(() => API.get("/health").then((res) => res.data)),
  brokerStatus: () => API.get("/broker/status").then((res) => res.data),
  dhanLogin: (payload: { client_id: string; access_token: string; persist?: boolean }) =>
    API.post("/broker/dhan/login", payload).then((res) => res.data),
  getSummary: () => API.get("/dashboard/summary").then((res) => res.data),
  operationsStatus: () => API.get("/dashboard/operations").then((res) => res.data),
  auditTrail: () => API.get("/dashboard/audit-trail", { params: { limit: 20 } }).then((res) => res.data),
  getStrategies: () => API.get("/trading/strategies").then((res) => res.data),
  strategies: () => API.get("/trading/strategies").then((res) => res.data),
  candles: (symbol: string, interval = "5m") =>
    API.get(`/market/candles/${symbol}`, { params: { interval } }).then((res) => res.data),
  storedCandles: (symbol: string, interval = "1m", limit = 100) =>
    API.get(`/market/stored/${symbol}`, { params: { interval, limit } }).then((res) => res.data),
  marketStoreStatus: (symbol = "NIFTY", interval = "1m") =>
    API.get("/market/store/status", { params: { symbol, interval } }).then((res) => res.data),
  getPrice: () => API.get("/market/price").then((res) => res.data),
  optionChain: (symbol = "NIFTY") =>
    API.get(`/market/option-chain/${symbol}`).then((res) => res.data),
  runSignals: (payload: SignalPayload) =>
    API.post("/trading/signals", payload).then((res) => res.data),
  executeOrder: (payload: unknown) =>
    API.post("/execution/order", payload).then((res) => res.data),
  executeAutoPaper: (payload: unknown = {}) =>
    API.post("/execution/auto-paper", payload).then((res) => res.data),
  execution: (payload: unknown) =>
    API.post("/execution/order", payload).then((res) => res.data),
  runAnalysis: (payload: unknown) =>
    API.post("/dashboard/live-analysis/jobs", payload).then((res) => res.data),
  getJobs: () => API.get("/dashboard/live-analysis/jobs").then((res) => res.data),
  jobs: () => API.get("/dashboard/live-analysis/jobs").then((res) => res.data),
  latestSignals: () => API.get("/api/signals/latest").then((res) => res.data),
  paperTrades: () => API.get("/api/trades/paper").then((res) => res.data),
  riskStatus: () => API.get("/api/risk/status").then((res) => res.data),
  backtestStrategy: (strategy: string) =>
    API.get(`/api/strategies/${strategy}/backtest`).then((res) => res.data),
};
