import { useEffect, useState } from "react";
import { api } from "../api";
import Loader from "../components/Loader";
import { useUiMode } from "../hooks/useUiMode";
import { localizeTimestamps } from "../utils/time";

const backtestStrategy = "amd";

function numeric(value: unknown, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function formatMoney(value: unknown) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(numeric(value));
}

function formatPercent(value: unknown) {
  const parsed = numeric(value);
  const percent = parsed > 0 && parsed <= 1 ? parsed * 100 : parsed;
  return `${percent.toFixed(1).replace(/\.0$/, "")}%`;
}

function StatusPill({ label }: { label: string }) {
  const normalized = label.toUpperCase();
  const className = normalized === "ACTIVE"
    ? "status-pill"
    : normalized === "STALE" || normalized === "WARNING"
      ? "status-pill stale"
      : "status-pill error";
  return <span className={className}>{label}</span>;
}

function hasBacktestTrades(backtest: any) {
  return Number(backtest?.metrics?.total_trades ?? 0) > 0;
}

export default function ProfessionalSignals() {
  const [signals, setSignals] = useState<any>(null);
  const [trades, setTrades] = useState<any[]>([]);
  const [risk, setRisk] = useState<any>(null);
  const [backtest, setBacktest] = useState<any>(null);
  const [journal, setJournal] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const developerMode = useUiMode() === "developer";

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.latestSignals(),
      api.tradeJournal(),
      api.riskEngine(),
      api.runBacktestingModule({ symbol: "NIFTY", strategy_name: backtestStrategy, min_score: 0 }),
    ])
      .then(([signalData, journalData, riskData, backtestData]) => {
        setSignals(signalData);
        setJournal(journalData);
        setTrades(Array.isArray(journalData?.recent_trades) ? journalData.recent_trades : []);
        setRisk(riskData?.summary ?? riskData);
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
              <div className="signal-summary">
                <span>
                  <strong>{hasBacktestTrades(backtest) ? formatPercent(backtest?.metrics?.win_rate) : "No trades yet"}</strong>
                  Win rate
                  <small>Run backtest to calculate performance.</small>
                </span>
                <span>
                  <strong>{hasBacktestTrades(backtest) ? numeric(backtest?.metrics?.sharpe_ratio).toFixed(2) : "Backtest not run"}</strong>
                  Sharpe
                  <small>Run backtest to calculate performance.</small>
                </span>
                <span>
                  <strong>{hasBacktestTrades(backtest) ? backtest?.metrics?.total_trades ?? 0 : "No trades yet"}</strong>
                  Trades
                  <small>Run backtest to calculate performance.</small>
                </span>
              </div>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Point</th>
                      <th>Equity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(backtest?.equity_curve ?? []).slice(-5).map((point: any) => (
                      <tr key={`equity-${point.index}`}>
                        <td>{point.index}</td>
                        <td>{formatMoney(point.equity)}</td>
                      </tr>
                    ))}
                    {(!backtest?.equity_curve || backtest.equity_curve.length === 0) && (
                      <tr>
                        <td colSpan={2}>No equity curve available yet.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              {developerMode && (
                <details className="technical-details" open>
                  <summary>Backtest API Payload</summary>
                  <pre>{JSON.stringify(localizeTimestamps(backtest ?? {}), null, 2)}</pre>
                </details>
              )}
            </div>
            <div className="form-panel signal-panel">
              <div className="form-panel-header">
                <div>
                  <h2>Paper Trades</h2>
                  <p>{journal?.total_trades ?? trades.length} journal rows | {formatPercent(journal?.win_rate)} win rate | {formatMoney(journal?.pnl)} PnL</p>
                </div>
              </div>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Symbol</th>
                      <th>Side</th>
                      <th>Status</th>
                      <th>PnL</th>
                      <th>Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades.slice(0, 8).map((trade: any, index) => (
                      <tr key={trade.id ?? index}>
                        <td>{trade.symbol ?? "-"}</td>
                        <td>{trade.side ?? "-"}</td>
                        <td>{trade.status ?? "-"}</td>
                        <td>{formatMoney(trade.pnl)}</td>
                        <td>{trade.created_at ? new Date(trade.created_at).toLocaleString() : "-"}</td>
                      </tr>
                    ))}
                    {trades.length === 0 && (
                      <tr>
                        <td colSpan={5}>No paper trades recorded yet.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              {developerMode && (
                <details className="technical-details" open>
                  <summary>Paper Trades API Payload</summary>
                  <pre>{JSON.stringify(localizeTimestamps(trades.slice(0, 10)), null, 2)}</pre>
                </details>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}
