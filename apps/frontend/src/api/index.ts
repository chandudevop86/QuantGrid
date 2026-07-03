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
  h1_candles?: SignalPayload["candles"];
  h4_candles?: SignalPayload["candles"];
  mtf_candles?: SignalPayload["candles"];
  m15_candles?: SignalPayload["candles"];
  m5_candles?: SignalPayload["candles"];
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
  brokerCircuitBreakerStatus: () => API.get("/broker/circuit-breaker/status").then((res) => res.data),
  dhanLogin: (payload: { client_id: string; access_token: string; persist?: boolean }) =>
    API.post("/broker/dhan/login", payload).then((res) => res.data),
  getSummary: () => API.get("/dashboard/summary").then((res) => res.data),
  operationsStatus: () =>
    API.get("/dashboard/operations")
      .then((res) => res.data)
      .catch(() => API.get("/operations/status").then((res) => res.data)),
  auditTrail: () => API.get("/audit/logs", { params: { limit: 50 } }).then((res) => res.data),
  getStrategies: () => API.get("/trading/strategies").then((res) => res.data),
  strategies: () => API.get("/trading/strategies").then((res) => res.data),
  candles: (symbol: string, interval = "5m") =>
    API.get(`/market/candles/${symbol}`, { params: { interval } }).then((res) => res.data),
  storedCandles: (symbol: string, interval = "1m", limit = 100) =>
    API.get(`/market/stored/${symbol}`, { params: { interval, limit } }).then((res) => res.data),
  marketStoreStatus: (symbol = "NIFTY", interval = "1m") =>
    API.get("/market/store/status", { params: { symbol, interval } }).then((res) => res.data),
  marketProviderStatus: (symbol = "NIFTY", interval = "1m") =>
    API.get("/market/provider/status", { params: { symbol, interval } }).then((res) => res.data),
  marketFeedHealth: (symbol = "NIFTY", interval = "1m") =>
    API.get("/market/feed/health", { params: { symbol, interval } }).then((res) => res.data),
  ltp: (symbol = "NIFTY") => API.get(`/market/ltp/${symbol}`).then((res) => res.data),
  getPrice: () => API.get("/market/price").then((res) => res.data),
  optionChain: (symbol = "NIFTY") =>
    API.get(`/market/option-chain/${symbol}`).then((res) => res.data),
  optionChainEngine: (symbol = "NIFTY") =>
    API.get(`/modules/option-chain/${symbol}`).then((res) => res.data),
  liveNseOptionChain: (symbol = "NIFTY") =>
    API.get(`/modules/option-chain/${symbol}/live-nse`).then((res) => res.data),
  historicalOptionChain: (symbol = "NIFTY") =>
    API.get(`/modules/option-chain/${symbol}/historical`).then((res) => res.data),
  runBacktestingModule: (payload: unknown = {}) =>
    API.post("/modules/backtesting", payload).then((res) => res.data),
  backtestingComparison: (payload: unknown = {}) =>
    API.post("/modules/backtesting/comparison", payload).then((res) => res.data),
  riskEngine: () => API.get("/modules/risk-engine").then((res) => res.data),
  tradeJournal: () => API.get("/modules/trade-journal").then((res) => res.data),
  tradeJournalRows: (params: Record<string, string> = {}) =>
    API.get("/api/trades/journal", { params })
      .then((res) => res.data)
      .catch(() => API.get("/trades/journal", { params }).then((res) => res.data)),
  tradeJournalEntry: (id: number) =>
    API.get(`/api/trades/journal/${id}`)
      .then((res) => res.data)
      .catch(() => API.get(`/trades/journal/${id}`).then((res) => res.data)),
  createTradeJournalEntry: (payload: unknown) =>
    API.post("/api/trades/journal", payload)
      .then((res) => res.data)
      .catch(() => API.post("/trades/journal", payload).then((res) => res.data)),
  updateTradeJournalEntry: (id: number, payload: unknown) =>
    API.patch(`/api/trades/journal/${id}`, payload)
      .then((res) => res.data)
      .catch(() => API.patch(`/trades/journal/${id}`, payload).then((res) => res.data)),
  modulesDashboard: () => API.get("/modules/dashboard").then((res) => res.data),
  runSignals: (payload: SignalPayload) =>
    API.post("/trading/signals", payload).then((res) => res.data),
  marketCopilot: (symbol = "NIFTY") =>
    API.get("/trading/copilot/market", { params: { symbol } }).then((res) => res.data),
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
  latestSignals: () =>
    API.get("/api/signals")
      .then((res) => res.data)
      .catch(() => API.get("/signals").then((res) => res.data)),
  signalsAudit: () =>
    API.get("/api/signals/audit")
      .then((res) => res.data)
      .catch(() => API.get("/signals/audit").then((res) => res.data)),
  systemAudit: () =>
    API.get("/api/system/audit")
      .then((res) => res.data)
      .catch(() => API.get("/system/audit").then((res) => res.data)),
  paperTrades: () =>
    API.get("/api/trades/paper")
      .then((res) => res.data)
      .catch(() => API.get("/trades/paper").then((res) => res.data)),
  riskStatus: () =>
    API.get("/api/risk/status")
      .then((res) => res.data)
      .catch(() => API.get("/risk/status").then((res) => res.data)),
  portfolioRiskDashboard: () => API.get("/risk/dashboard").then((res) => res.data),
  positionSummary: () => API.get("/positions/summary").then((res) => res.data),
  openPositions: () => API.get("/positions/open").then((res) => res.data),
  closedPositions: () => API.get("/positions/closed").then((res) => res.data),
  backtestStrategy: (strategy: string) =>
    API.get(`/api/strategies/${strategy}/backtest`)
      .then((res) => res.data)
      .catch(() => API.get(`/strategies/${strategy}/backtest`).then((res) => res.data)),
  investingDashboard: () => API.get("/investing/dashboard").then((res) => res.data),
  institutionalDashboard: () => API.get("/institutional/dashboard").then((res) => res.data),
  stockResearch: () => API.get("/investing/stocks/research").then((res) => res.data),
  stockTopPicks: () => API.get("/investing/stocks/top-picks").then((res) => res.data),
  multibaggerPredictor: () => API.get("/investing/stocks/multibagger-predictor").then((res) => res.data),
  mutualFundResearch: () => API.get("/investing/mutual-funds/research").then((res) => res.data),
  mutualFundTopPicks: () => API.get("/investing/mutual-funds/top-picks").then((res) => res.data),
  dataQualityDashboard: (symbol = "NIFTY", interval = "1m") =>
    API.get("/data-quality/dashboard", { params: { symbol, interval } }).then((res) => res.data),
  securityDashboard: () => API.get("/security/dashboard").then((res) => res.data),
  securityFindings: () => API.get("/security/findings").then((res) => res.data),
};
