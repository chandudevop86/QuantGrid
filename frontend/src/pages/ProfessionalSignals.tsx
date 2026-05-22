import { useEffect, useState } from "react";
import { api } from "../api";
import Loader from "../components/Loader";
import { localizeTimestamps } from "../utils/time";

const backtestStrategy = "amd";

function StatusPill({ label }: { label: string }) {
  const normalized = label.toUpperCase();
  const className = normalized === "ACTIVE"
    ? "status-pill"
    : normalized === "STALE" || normalized === "WARNING"
      ? "status-pill stale"
      : "status-pill error";
  return <span className={className}>{label}</span>;
}

export default function ProfessionalSignals() {
  const [signals, setSignals] = useState<any>(null);
  const [trades, setTrades] = useState<any[]>([]);
  const [risk, setRisk] = useState<any>(null);
  const [backtest, setBacktest] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.latestSignals(),
      api.paperTrades(),
      api.riskStatus(),
      api.backtestStrategy(backtestStrategy),
    ])
      .then(([signalData, tradeData, riskData, backtestData]) => {
        setSignals(signalData);
        setTrades(Array.isArray(tradeData?.trades) ? tradeData.trades : []);
        setRisk(riskData);
        setBacktest(backtestData);
      })
      .catch((err: any) => setError(err?.message ?? "Failed to load professional signal dashboard."))
      .finally(() => setLoading(false));
  }, []);

  return (
    <section className="dashboard-page">
      <div className="page-heading">
        <h1>Signals</h1>
        <p>Active, rejected, stale, risk, journal, and backtest view.</p>
      </div>

      {loading && <Loader label="Loading signal dashboard..." />}
      {error && <div className="alert alert-error">{error}</div>}

      {!loading && !error && (
        <>
          <div className="metric-grid">
            <div className="metric-card metric-card-good">
              <span className="metric-label">Active Signals</span>
              <strong className="metric-value">{signals?.active_signals?.length ?? 0}</strong>
              <span className="metric-helper">Executable after risk gate</span>
            </div>
            <div className="metric-card metric-card-warn">
              <span className="metric-label">Rejected Signals</span>
              <strong className="metric-value">{signals?.rejected_signals?.length ?? 0}</strong>
              <span className="metric-helper">Low score, choppy, or MTF conflict</span>
            </div>
            <div className="metric-card metric-card-warn">
              <span className="metric-label">Stale Signals</span>
              <strong className="metric-value">{signals?.stale_signals?.length ?? 0}</strong>
              <span className="metric-helper">Older than latest candle / 2m limit</span>
            </div>
            <div className="metric-card">
              <span className="metric-label">Risk Status</span>
              <strong className="metric-value">{risk?.trades_today ?? 0}/{risk?.max_trades_per_day ?? "-"}</strong>
              <span className="metric-helper">Daily PnL {risk?.daily_pnl ?? 0}</span>
            </div>
          </div>

          <div className="dashboard-section">
            <div className="section-header">
              <h2>Latest Signal Gate</h2>
              <span>{signals?.latest_candle_time ?? "-"}</span>
            </div>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Status</th>
                    <th>Strategy</th>
                    <th>Side</th>
                    <th>Score</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {(signals?.active_signals ?? []).map((signal: any) => (
                    <tr key={`${signal.strategy_name}-${signal.timestamp}-active`}>
                      <td><StatusPill label="ACTIVE" /></td>
                      <td>{signal.strategy_name}</td>
                      <td>{signal.side}</td>
                      <td>{signal.score ?? signal.total_score ?? "-"}</td>
                      <td>OK</td>
                    </tr>
                  ))}
                  {(signals?.rejected_signals ?? []).map((item: any, index: number) => (
                    <tr key={`rejected-${index}`}>
                      <td><StatusPill label="REJECTED" /></td>
                      <td>{item.signal?.strategy_name}</td>
                      <td>{item.signal?.side}</td>
                      <td>{item.decision?.score}</td>
                      <td>{item.decision?.reason}</td>
                    </tr>
                  ))}
                  {(signals?.stale_signals ?? []).map((item: any, index: number) => (
                    <tr key={`stale-${index}`}>
                      <td><StatusPill label="STALE" /></td>
                      <td>{item.signal?.strategy_name}</td>
                      <td>{item.signal?.side}</td>
                      <td>{item.decision?.score}</td>
                      <td>{item.decision?.signal_age_minutes}m old</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="strategy-signal-grid">
            <div className="form-panel signal-panel">
              <div className="form-panel-header">
                <div>
                  <h2>Backtest Metrics</h2>
                  <p>{backtestStrategy.toUpperCase()} / NIFTY / 1m</p>
                </div>
              </div>
              <pre>{JSON.stringify(localizeTimestamps(backtest?.metrics ?? {}), null, 2)}</pre>
            </div>
            <div className="form-panel signal-panel">
              <div className="form-panel-header">
                <div>
                  <h2>Paper Trades</h2>
                  <p>{trades.length} journal rows</p>
                </div>
              </div>
              <pre>{JSON.stringify(localizeTimestamps(trades.slice(0, 10)), null, 2)}</pre>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
