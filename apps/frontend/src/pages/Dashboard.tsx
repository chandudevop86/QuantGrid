import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import Loader from "../components/Loader";
import MetricCard from "../components/MetricCard";
import SystemHealthWidget from "../components/SystemHealthWidget";
import { useLiveJobs } from "../hooks/useLiveJobs";
import { getCurrentUiMode, setCurrentUiMode, type UiMode } from "../mode";
import { hasAuthToken } from "../roles";
import { createSocket } from "../socket";
import { getMarketStatusClass, getMarketStatusLabel } from "../utils/marketStatus";

function isActiveJob(job: any) {
  return ["queued", "running"].includes(String(job?.status ?? "").toLowerCase());
}

type HealthTone = "ok" | "warn" | "fail";

function statusTone(tone: HealthTone) {
  if (tone === "ok") return "health-ok";
  if (tone === "warn") return "health-warn";
  return "health-fail";
}

function formatMoney(value: unknown) {
  const numeric = Number(value ?? 0);
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(Number.isFinite(numeric) ? numeric : 0);
}

function formatPercent(value: unknown) {
  const numeric = Number(value ?? 0);
  return `${Number.isFinite(numeric) ? numeric.toFixed(2).replace(/\.?0+$/, "") : "0"}%`;
}

function formatTime(value: unknown) {
  if (!value) return "-";
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? "-" : date.toLocaleTimeString();
}

function friendlyMarketMessage(market: any) {
  if (market?.valid_for_execution) return "Market data is fresh enough for confirmation checks.";
  if (market?.state === "holiday") return "Market is closed for a holiday.";
  if (market?.session_state === "closed") return "Market session is closed.";
  return "Current market conditions do not meet confirmation criteria.";
}

function brokerLoginValue(brokerStatus: any) {
  if (!brokerStatus) return "Checking";
  if (brokerStatus.provider === "dhan") {
    if (brokerStatus.connected) return "Dhan OK";
    if (brokerStatus.configured) return "Dhan Issue";
    return "Dhan Missing";
  }
  return brokerStatus.configured ? String(brokerStatus.provider ?? "Broker").toUpperCase() : "Paper";
}

function brokerLoginTone(brokerStatus: any) {
  if (brokerStatus?.connected) return "good";
  return brokerStatus?.configured ? "warn" : "warn";
}

function useDashboardOperations(isAuthenticated: boolean) {
  const [operations, setOperations] = useState<any>(null);
  const [socketActive, setSocketActive] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated) {
      setOperations(null);
      setSocketActive(false);
      setError(null);
      return;
    }

    let active = true;
    let socket: WebSocket | null = null;
    let fallbackId: number | null = null;
    let reconnectId: number | null = null;

    const load = async () => {
      try {
        const data = await api.operationsStatus();
        if (!active) return;
        setOperations(data);
        setError(null);
      } catch {
        if (active) setError("Dashboard API is not available yet.");
      }
    };

    const stopFallback = () => {
      if (fallbackId !== null) {
        window.clearInterval(fallbackId);
        fallbackId = null;
      }
    };

    const startFallback = () => {
      if (fallbackId !== null) return;
      void load();
      fallbackId = window.setInterval(load, 15000);
    };

    const connect = () => {
      socket = createSocket();

      socket.onopen = () => {
        if (!active) return;
        setSocketActive(true);
        stopFallback();
        void load();
      };

      socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          if (message?.type === "dashboard_status" && message?.payload) {
            setOperations(message.payload);
            setError(null);
          }
        } catch {
          if (active) setError("Received an invalid dashboard status update.");
        }
      };

      socket.onerror = () => socket?.close();

      socket.onclose = () => {
        if (!active) return;
        setSocketActive(false);
        startFallback();
        reconnectId = window.setTimeout(connect, 5000);
      };
    };

    void load();
    connect();

    return () => {
      active = false;
      stopFallback();
      if (reconnectId !== null) window.clearTimeout(reconnectId);
      socket?.close();
    };
  }, [isAuthenticated]);

  return { operations, socketActive, error };
}

export default function Dashboard() {
  const [summary, setSummary] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [marketStore, setMarketStore] = useState<any>(null);
  const [marketProvider, setMarketProvider] = useState<any>(null);
  const [brokerStatus, setBrokerStatus] = useState<any>(null);
  const [positionSummary, setPositionSummary] = useState<any>(null);
  const [modules, setModules] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(hasAuthToken());
  const [uiMode, setUiMode] = useState<UiMode>(getCurrentUiMode());
  const { jobs, error: jobsError, socketConnected: jobsSocketConnected } = useLiveJobs();
  const { operations, socketActive, error: operationsError } = useDashboardOperations(isAuthenticated);

  useEffect(() => {
    const syncAuth = () => setIsAuthenticated(hasAuthToken());
    const syncUiMode = () => setUiMode(getCurrentUiMode());
    window.addEventListener("quantgrid-role-change", syncAuth);
    window.addEventListener("storage", syncAuth);
    window.addEventListener("quantgrid-ui-mode-change", syncUiMode);
    return () => {
      window.removeEventListener("quantgrid-role-change", syncAuth);
      window.removeEventListener("storage", syncAuth);
      window.removeEventListener("quantgrid-ui-mode-change", syncUiMode);
    };
  }, []);

  useEffect(() => {
    setError(null);
    if (!isAuthenticated) {
      setSummary(null);
      setMarketStore(null);
      setMarketProvider(null);
      setBrokerStatus(null);
      setPositionSummary(null);
      setModules(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    Promise.all([
      api.getSummary(),
      api.marketStoreStatus("NIFTY", "1m"),
      api.marketProviderStatus("NIFTY", "1m").catch(() => null),
      api.brokerStatus(),
      api.positionSummary().catch(() => null),
      api.modulesDashboard().catch(() => null),
    ])
      .then(([summaryData, marketStoreData, marketProviderData, brokerData, positionData, modulesData]) => {
        setSummary(summaryData);
        setMarketStore(marketStoreData);
        setMarketProvider(marketProviderData);
        setBrokerStatus(brokerData);
        setPositionSummary(positionData);
        setModules(modulesData);
      })
      .catch(() => setError("Dashboard API is not available yet."))
      .finally(() => setLoading(false));
  }, [isAuthenticated]);

  const activeJobs = jobs.filter(isActiveJob).length;
  const lastUpdated = summary?.updated_at
    ? new Date(summary.updated_at).toLocaleString()
    : "Not available";
  const market = operations?.market_status;
  const health = operations?.system_health;
  const risk = operations?.risk_summary;
  const observability = operations?.observability;
  const backtest = operations?.backtest_context;
  const liveTrading = risk?.live_trading_enabled || risk?.execution_mode === "LIVE";
  const marketStatusLabel = getMarketStatusLabel(market);
  const feedBadge =
    marketProvider?.feed_status === "LIVE FEED"
      ? "🟢 LIVE FEED"
      : marketProvider?.feed_status === "DELAYED FEED"
        ? "🟡 DELAYED FEED"
        : marketProvider?.feed_status === "FEED DOWN"
          ? "🔴 FEED DOWN"
          : "⚫ DEMO/YAHOO MODE";

  const healthItems = useMemo(() => {
    const redisConfigured = health?.redis?.message !== "REDIS_URL is not configured.";
    const brokerConfigured = health?.broker?.provider !== "paper" || brokerStatus?.configured === true;
    const brokerConnected = health?.broker?.connected === true || brokerStatus?.connected === true;
    const websocketConnected = socketActive || health?.websocket?.active === true;

    return [
      { label: "API", tone: health?.api?.healthy === true ? "ok" : "fail", status: health?.api?.healthy === true ? "OK" : "FAIL" },
      { label: "DB", tone: health?.db?.healthy === true ? "ok" : "fail", status: health?.db?.healthy === true ? "OK" : "FAIL" },
      {
        label: "Redis",
        tone: health?.redis?.connected === true ? "ok" : redisConfigured ? "fail" : "warn",
        status: health?.redis?.connected === true ? "OK" : redisConfigured ? "FAIL" : "OFF",
      },
      {
        label: "WebSocket",
        tone: websocketConnected ? "ok" : "warn",
        status: websocketConnected ? "OK" : "POLL",
      },
      {
        label: "Broker",
        tone: brokerConnected || !brokerConfigured ? "ok" : "warn",
        status: brokerConnected ? "OK" : brokerConfigured ? "CHECK" : "PAPER",
      },
    ] as Array<{ label: string; tone: HealthTone; status: string }>;
  }, [brokerStatus, health, socketActive]);
  const failingHealthItems = healthItems.filter((item) => item.tone === "fail");
  const warningHealthItems = healthItems.filter((item) => item.tone === "warn");
  const healthSummary =
    failingHealthItems.length > 0 ? "Needs attention" : warningHealthItems.length > 0 ? "Review" : "Healthy";

  const diagnostics = operations?.diagnostics ?? {
    trader_message: friendlyMarketMessage(market),
    validation_summary: market?.valid_for_execution ? "Confirmation checks available." : "Confirmation criteria are not met.",
    technical_details: market?.warnings ?? [],
  };
  const optionModule = modules?.option_chain;
  const backtestModule = modules?.backtesting;
  const riskModule = modules?.risk_engine;
  const journalModule = modules?.trade_journal;

  return (
    <section className="dashboard-page">
      <div className="page-heading dashboard-heading">
        <div>
          <h1>QuantGrid Dashboard</h1>
          <p>Production trading status, operational health, and execution safety.</p>
        </div>
        <div className="mode-toggle" aria-label="Dashboard display mode">
          {(["trader", "developer"] as UiMode[]).map((mode) => (
            <button
              key={mode}
              className={uiMode === mode ? "active" : ""}
              type="button"
              onClick={() => {
                setCurrentUiMode(mode);
                setUiMode(mode);
              }}
            >
              {mode === "trader" ? "Trader" : "Developer"}
            </button>
          ))}
        </div>
      </div>

      {liveTrading && (
        <div className="alert alert-error live-warning" role="alert">
          LIVE TRADING ENABLED
        </div>
      )}

      {!isAuthenticated && (
        <div className="alert alert-warning" role="status">
          Login with an authorized account to view dashboard data and trading workflows.
        </div>
      )}

      {isAuthenticated && loading && <Loader label="Loading dashboard..." />}
      {(error || jobsError || operationsError) && <p className="error-text">{error ?? jobsError ?? operationsError}</p>}

      {isAuthenticated && !loading && !error && !jobsError && (
        <>
          <div className="status-panel-grid">
            <div className="status-panel">
              <div className="status-panel-header">
                <span>Market Status</span>
                <strong className={`market-status-text ${getMarketStatusClass(marketStatusLabel)}`}>
                  {marketStatusLabel}
                </strong>
              </div>
              <div className="status-panel-body">
                <span>System state: {marketStatusLabel}</span>
                <span>Feed delay: {market?.feed_delay_seconds ?? "-"}s</span>
                <span>Last candle: {formatTime(market?.last_candle_timestamp)}</span>
                <span>Session: {market?.session_state ?? "unknown"}</span>
                <span>{friendlyMarketMessage(market)}</span>
              </div>
            </div>

            <div className="status-panel">
              <div className="status-panel-header">
                <span>System Health</span>
                <strong>{healthSummary}</strong>
              </div>
              <div className="health-dot-grid">
                {healthItems.map((item) => (
                  <span key={item.label} className={statusTone(item.tone)}>
                    <strong>{item.label}</strong>
                    <small>{item.status}</small>
                  </span>
                ))}
              </div>
            </div>

            <div className="status-panel risk-panel">
              <div className="status-panel-header">
                <span>Risk Summary</span>
                <strong>{risk?.execution_mode ?? "PAPER"}</strong>
              </div>
              <div className="status-panel-body">
                <span>Trades today: {risk?.trades_today ?? 0}</span>
                <span>Daily PnL: {formatMoney(risk?.daily_pnl)}</span>
                <span>Loss remaining: {formatMoney(risk?.daily_loss_remaining)}</span>
                <span>Consecutive losses: {risk?.consecutive_losses ?? 0}</span>
                <span>Risk state: {risk?.active_risk_state ?? "UNKNOWN"}</span>
              </div>
            </div>
          </div>

          <SystemHealthWidget operations={operations} websocketConnected={socketActive} />

          <div className="metric-grid">
            <MetricCard
              label="API Status"
              value={summary?.status ?? "unknown"}
              helper={`Updated ${lastUpdated}`}
              tone={summary?.status === "ready" ? "good" : "warn"}
            />
            <MetricCard
              label="Realtime Channel"
              value={socketActive ? "WebSocket" : "Fallback"}
              helper={jobsSocketConnected ? "Job stream active" : "Polling only after socket failure"}
              tone={socketActive ? "good" : "warn"}
            />
            <MetricCard
              label="Active Jobs"
              value={activeJobs}
              helper={`${jobs.length} total jobs`}
            />
            <MetricCard
              label="Broker Login"
              value={brokerLoginValue(brokerStatus)}
              helper={brokerStatus?.message ?? "Real-money orders disabled"}
              tone={brokerLoginTone(brokerStatus)}
            />
            <MetricCard
              label="Market Provider"
              value={marketProvider?.provider_name ?? marketProvider?.provider ?? "Unknown"}
              helper={`${marketProvider?.suitability ?? (marketProvider?.live_suitable ? "live" : "paper")} - ${feedBadge}`}
              tone={marketProvider?.live_suitable && marketProvider?.fresh ? "good" : "warn"}
            />
            <MetricCard
              label="Provider Fetch"
              value={marketProvider?.fresh ? "Fresh" : "Stale"}
              helper={marketProvider?.latest_fetch_time || marketProvider?.latest_fetch_at || marketProvider?.last_tick_time ? `Latest ${new Date(marketProvider.latest_fetch_time ?? marketProvider.latest_fetch_at ?? marketProvider.last_tick_time).toLocaleTimeString()}` : "No fetch yet"}
              tone={marketProvider?.fresh ? "good" : "warn"}
            />
            <MetricCard
              label="Feed Delay"
              value={`${marketProvider?.feed_delay_seconds ?? observability?.feed_delay_seconds ?? 0}s`}
              helper={`Cache ${marketProvider?.cache_status ?? "unknown"}`}
              tone={(marketProvider?.feed_delay_seconds ?? observability?.feed_delay_seconds ?? 999) > 10 ? "warn" : "good"}
            />
            <MetricCard
              label="Stored Live Candles"
              value={marketStore?.candles ?? 0}
              helper={marketStore?.latest_candle_at ? `Latest ${new Date(marketStore.latest_candle_at).toLocaleTimeString()}` : "NIFTY 1m database"}
            />
          </div>

          <div className="dashboard-section">
            <div className="section-header">
              <h2>QuantGrid Modules</h2>
              <span>{modules ? "Live" : "Loading"}</span>
            </div>
            <div className="module-grid">
              <div className="module-panel">
                <div className="module-panel-header">
                  <span>Option Chain Engine</span>
                  <strong>{optionModule?.symbol ?? "NIFTY"}</strong>
                </div>
                <div className="status-panel-body">
                  <span>ATM strike: {optionModule?.atm_strike ?? "-"}</span>
                  <span>PCR: {optionModule?.pcr ?? "-"}</span>
                  <span>Max pain: {optionModule?.max_pain ?? "-"}</span>
                  <span>Greeks: {optionModule?.greek_model ?? "Black-Scholes demo"}</span>
                </div>
              </div>

              <div className="module-panel">
                <div className="module-panel-header">
                  <span>Backtesting</span>
                  <strong>{backtestModule?.metrics?.total_trades ?? 0} trades</strong>
                </div>
                <div className="status-panel-body">
                  <span>PnL: {formatMoney(backtestModule?.metrics?.pnl)}</span>
                  <span>Win rate: {Math.round(Number(backtestModule?.metrics?.win_rate ?? 0) * 100)}%</span>
                  <span>Max drawdown: {Math.round(Number(backtestModule?.metrics?.max_drawdown ?? 0) * 100)}%</span>
                  <span>Equity points: {backtestModule?.equity_curve?.length ?? 0}</span>
                </div>
              </div>

              <div className="module-panel">
                <div className="module-panel-header">
                  <span>Risk Engine</span>
                  <strong>{riskModule?.state ?? risk?.active_risk_state ?? "normal"}</strong>
                </div>
                <div className="status-panel-body">
                  <span>Daily loss: {riskModule?.checks?.daily_loss ? "OK" : "Blocked"}</span>
                  <span>Trades/day: {riskModule?.checks?.trades_per_day ? "OK" : "Blocked"}</span>
                  <span>Open positions: {riskModule?.checks?.open_positions ? "OK" : "Blocked"}</span>
                  <span>Kill switch: {riskModule?.checks?.kill_switch ? "Ready" : "Active"}</span>
                </div>
              </div>

              <div className="module-panel">
                <div className="module-panel-header">
                  <span>Trade Journal</span>
                  <strong>{journalModule?.closed_trades ?? 0} closed</strong>
                </div>
                <div className="status-panel-body">
                  <span>PnL: {formatMoney(journalModule?.pnl)}</span>
                  <span>Win rate: {Math.round(Number(journalModule?.win_rate ?? 0) * 100)}%</span>
                  <span>Avg win: {formatMoney(journalModule?.avg_win)}</span>
                  <span>Avg loss: {formatMoney(journalModule?.avg_loss)}</span>
                </div>
              </div>
            </div>
          </div>

          <div className="dashboard-section">
            <div className="section-header">
              <h2>Risk Summary</h2>
              <span>{risk?.risk_configured ? "Configured" : "Using defaults"}</span>
            </div>
            {liveTrading && !risk?.risk_configured && (
              <div className="alert alert-error" role="alert">
                Live trading blocked until capital, risk per trade, and max daily loss are configured.
              </div>
            )}
            <div className="risk-summary-grid">
              <span>
                <small>Capital</small>
                <strong>{formatMoney(risk?.capital ?? 100000)}</strong>
              </span>
              <span>
                <small>Risk per trade</small>
                <strong>{formatPercent(risk?.risk_per_trade_pct ?? 1)}</strong>
                <small>{formatMoney(risk?.risk_per_trade_amount ?? 1000)}</small>
              </span>
              <span>
                <small>Open positions</small>
                <strong>{risk?.open_positions ?? summary?.open_positions ?? 0}</strong>
              </span>
              <span>
                <small>Current exposure</small>
                <strong>{formatMoney(risk?.current_exposure ?? 0)}</strong>
              </span>
              <span>
                <small>Paper/live mode</small>
                <strong>{risk?.execution_mode ?? "PAPER"}</strong>
              </span>
              <span>
                <small>Max daily loss</small>
                <strong>{formatMoney(risk?.max_daily_loss ?? 3000)}</strong>
              </span>
            </div>
          </div>

          <div className="dashboard-section">
            <div className="section-header">
              <h2>Positions</h2>
              <span>{positionSummary?.open_positions ?? risk?.open_positions ?? 0} open</span>
            </div>
            <div className="risk-summary-grid">
              <span><small>Open positions</small><strong>{positionSummary?.open_positions ?? risk?.open_positions ?? 0}</strong></span>
              <span><small>Today's PnL</small><strong>{formatMoney(positionSummary?.todays_pnl ?? risk?.daily_pnl ?? 0)}</strong></span>
              <span><small>Current exposure</small><strong>{formatMoney(positionSummary?.current_exposure ?? risk?.current_exposure ?? 0)}</strong></span>
              <span><small>Realized PnL</small><strong>{formatMoney(positionSummary?.realized_pnl ?? risk?.realized_pnl ?? 0)}</strong></span>
              <span><small>Unrealized PnL</small><strong>{formatMoney(positionSummary?.unrealized_pnl ?? risk?.unrealized_pnl ?? 0)}</strong></span>
            </div>
          </div>

          <div className="dashboard-section">
            <div className="section-header">
              <h2>Execution Safety</h2>
              <span>{risk?.active_risk_state ?? "UNKNOWN"}</span>
            </div>
            <div className="execution-safety-grid">
              <span><small>Validation status</small><strong>{market?.valid_for_execution ? "Ready" : "Waiting"}</strong></span>
              <span><small>Risk status</small><strong>{risk?.active_risk_state ?? "UNKNOWN"}</strong></span>
              <span><small>Execution eligibility</small><strong>{market?.valid_for_execution && risk?.active_risk_state === "NORMAL" ? "Eligible" : "Blocked"}</strong></span>
              <span><small>Market session</small><strong>{market?.session_state ?? "unknown"}</strong></span>
            </div>
          </div>

          <div className="dashboard-section">
            <div className="section-header">
              <h2>Strategy Context</h2>
              <span>Backtest and replay</span>
            </div>
            <div className="strategy-context">
              <span><small>Historical win rate</small><strong>{backtest?.historical_trade_count ? `${Math.round((backtest?.historical_win_rate ?? 0) * 100)}%` : "No trades yet"}</strong><small>Run backtest to calculate performance.</small></span>
              <span><small>Sharpe ratio</small><strong>{backtest?.historical_trade_count ? backtest?.sharpe_ratio ?? 0 : "Backtest not run"}</strong><small>Run backtest to calculate performance.</small></span>
              <span><small>Recent outcomes</small><strong>{backtest?.recent_trade_outcomes?.length ?? 0}</strong></span>
            </div>
          </div>

          <div className="dashboard-section">
            <div className="section-header">
              <h2>Diagnostics</h2>
              <span>{uiMode === "trader" ? "Trader mode" : "Developer mode"}</span>
            </div>
            <div className="diagnostic-list">
              <span>{diagnostics.trader_message}</span>
              <span>{diagnostics.validation_summary}</span>
            </div>
            {uiMode === "developer" && (
              <details className="technical-details" open>
                <summary>Show Technical Details</summary>
                <pre>{JSON.stringify({ operations, summary, marketStore, marketProvider, brokerStatus }, null, 2)}</pre>
              </details>
            )}
          </div>

          {uiMode === "developer" && (
            <div className="dashboard-section">
              <div className="section-header">
                <h2>Operational Dashboard</h2>
                <span>{socketActive ? "WebSocket active" : "Polling fallback"}</span>
              </div>
              <div className="metric-grid observability-grid">
                <MetricCard label="WebSocket Connections" value={observability?.websocket_connections ?? 0} helper="Connected dashboard clients" />
                <MetricCard label="API Latency" value={observability?.api_latency_status ?? "tracked"} helper="Prometheus metric" />
                <MetricCard label="Signals" value={observability?.signal_generation_metrics ?? "tracked"} helper="Generation metrics" />
                <MetricCard label="Rejected Orders" value={observability?.rejected_order_metrics ?? "tracked"} helper="Safety rejection metric" />
                <MetricCard label="Redis" value={observability?.redis_healthy ? "OK" : "Review"} helper="Pub/sub and cache" tone={observability?.redis_healthy ? "good" : "warn"} />
                <MetricCard label="DB" value={observability?.db_healthy ? "OK" : "Review"} helper="Persistence health" tone={observability?.db_healthy ? "good" : "warn"} />
              </div>
            </div>
          )}

          <div className="dashboard-section">
            <div className="section-header">
              <h2>Recent Jobs</h2>
              <span>{jobs.length} total</span>
            </div>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Status</th>
                    <th>Symbol</th>
                    <th>Strategy</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.slice(0, 5).map((job) => (
                    <tr key={job.job_id ?? job.id}>
                      <td>{job.job_id ?? job.id}</td>
                      <td>{job.status ?? "unknown"}</td>
                      <td>{job.symbol ?? "-"}</td>
                      <td>{job.strategy ?? "-"}</td>
                    </tr>
                  ))}
                  {jobs.length === 0 && (
                    <tr>
                      <td colSpan={4}>No live-analysis jobs yet.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
