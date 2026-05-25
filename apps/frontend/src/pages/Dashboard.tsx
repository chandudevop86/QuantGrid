import { useEffect, useState } from "react";
import { api } from "../api";
import Loader from "../components/Loader";
import MetricCard from "../components/MetricCard";
import { useLiveJobs } from "../hooks/useLiveJobs";
import { hasAuthToken } from "../roles";

function isActiveJob(job: any) {
  return ["queued", "running"].includes(String(job?.status ?? "").toLowerCase());
}

export default function Dashboard() {
  const [summary, setSummary] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [marketStore, setMarketStore] = useState<any>(null);
  const [brokerStatus, setBrokerStatus] = useState<any>(null);
  const [operations, setOperations] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(hasAuthToken());
  const { jobs, error: jobsError } = useLiveJobs();

  useEffect(() => {
    const syncAuth = () => setIsAuthenticated(hasAuthToken());
    window.addEventListener("quantgrid-role-change", syncAuth);
    window.addEventListener("storage", syncAuth);
    return () => {
      window.removeEventListener("quantgrid-role-change", syncAuth);
      window.removeEventListener("storage", syncAuth);
    };
  }, []);

  useEffect(() => {
    setError(null);
    if (!isAuthenticated) {
      setSummary(null);
      setMarketStore(null);
      setBrokerStatus(null);
      setOperations(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    Promise.all([
      api.getSummary(),
      api.marketStoreStatus("NIFTY", "1m"),
      api.brokerStatus(),
      api.operationsStatus(),
    ])
      .then(([summaryData, marketStoreData, brokerData, operationsData]) => {
        setSummary(summaryData);
        setMarketStore(marketStoreData);
        setBrokerStatus(brokerData);
        setOperations(operationsData);
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
  const healthItems = [
    ["API", health?.api?.healthy],
    ["Redis", health?.redis?.connected],
    ["DB", health?.db?.healthy],
    ["WebSocket", health?.websocket?.active],
    ["Broker", health?.broker?.connected],
    ["Worker", health?.background_worker?.healthy],
  ];

  return (
    <section className="dashboard-page">
      <div className="page-heading">
        <div>
          <h1>QuantGrid Dashboard</h1>
          <p>Service health, live-analysis jobs, and trading activity at a glance.</p>
        </div>
      </div>

      {!isAuthenticated && (
        <div className="alert alert-warning" role="status">
          Login with an authorized account to view dashboard data and trading workflows.
        </div>
      )}

      {isAuthenticated && loading && <Loader label="Loading dashboard..." />}
      {(error || jobsError) && <p className="error-text">{error ?? jobsError}</p>}

      {isAuthenticated && !loading && !error && !jobsError && (
        <>
          <div className="status-panel-grid">
            <div className="status-panel">
              <div className="status-panel-header">
                <span>Market Status</span>
                <strong>{market?.label ?? "Checking"}</strong>
              </div>
              <div className="status-panel-body">
                <span>Feed delay: {market?.feed_delay_seconds ?? "-"}s</span>
                <span>
                  Last candle: {market?.last_candle_timestamp ? new Date(market.last_candle_timestamp).toLocaleTimeString() : "-"}
                </span>
                <span>Session: {market?.session_state ?? "unknown"}</span>
              </div>
            </div>

            <div className="status-panel">
              <div className="status-panel-header">
                <span>System Health</span>
                <strong>{healthItems.every(([, ok]) => ok === true) ? "Healthy" : "Needs attention"}</strong>
              </div>
              <div className="health-dot-grid">
                {healthItems.map(([label, ok]) => (
                  <span key={String(label)} className={ok ? "health-ok" : "health-warn"}>
                    {label}
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
                <span>Daily PnL: {risk?.daily_pnl ?? 0}</span>
                <span>Loss remaining: {risk?.daily_loss_remaining ?? "-"}</span>
                <span>Risk state: {risk?.active_risk_state ?? "UNKNOWN"}</span>
              </div>
            </div>
          </div>

          <div className="metric-grid">
            <MetricCard
              label="API Status"
              value={summary?.status ?? "unknown"}
              helper={`Updated ${lastUpdated}`}
              tone={summary?.status === "ready" ? "good" : "warn"}
            />
            <MetricCard
              label="Active Jobs"
              value={activeJobs}
              helper={`${jobs.length} total jobs`}
            />
            <MetricCard
              label="Open Positions"
              value={summary?.open_positions ?? 0}
              helper="Paper execution mode"
            />
            <MetricCard
              label="Broker Login"
              value={brokerStatus?.provider === "dhan" && brokerStatus?.connected ? "Dhan OK" : "Paper"}
              helper={brokerStatus?.message ?? "Real-money orders disabled"}
              tone={brokerStatus?.connected ? "good" : "warn"}
            />
            <MetricCard
              label="Stored Live Candles"
              value={marketStore?.candles ?? 0}
              helper={marketStore?.latest_candle_at ? `Latest ${new Date(marketStore.latest_candle_at).toLocaleTimeString()}` : "NIFTY 1m database"}
            />
          </div>

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
