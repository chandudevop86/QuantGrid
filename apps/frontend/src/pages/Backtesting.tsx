import { useEffect, useMemo, useState } from "react";
import { api } from "../api";

const defaultStrategies = ["amd", "breakout", "btst", "cbt", "crt_tbs", "mean_reversion", "mtf", "mtfa", "supply_demand"];
const quickStrategies = ["amd", "breakout", "mean_reversion", "supply_demand"];

type BacktestRun = {
  strategy: string;
  symbol?: string;
  metrics?: Record<string, number | string | null>;
  equity_curve?: Array<{ index: number; equity: number; time?: string }>;
  recent_outcomes?: Array<Record<string, unknown>>;
};

type BacktestComparison = {
  module?: string;
  symbol?: string;
  runs?: BacktestRun[];
  ranked?: BacktestRun[];
  best_strategy?: string | null;
  updated_at?: string;
};

function titleCase(value: string) {
  return value.split("_").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}

function number(value: unknown, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function formatNumber(value: unknown, digits = 2) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed.toFixed(digits) : "-";
}

function formatMoney(value: unknown) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "-";
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(parsed);
}

function formatPercent(value: unknown) {
  return `${formatNumber(value)}%`;
}

function bestRun(payload: BacktestComparison | null) {
  return payload?.ranked?.[0] ?? payload?.runs?.[0] ?? null;
}

export default function Backtesting() {
  const [payload, setPayload] = useState<BacktestComparison | null>(null);
  const [selected, setSelected] = useState("amd");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = (mode: "quick" | "full" = "quick") => {
    setLoading(true);
    const strategies = mode === "full" ? defaultStrategies : quickStrategies;
    api.backtestingComparison({ symbol: "NIFTY", strategies, min_score: 0, max_candles: mode === "full" ? 120 : 80 })
      .then((data) => {
        setPayload(data);
        setSelected(data?.best_strategy ?? "amd");
        setError(null);
      })
      .catch((err) => {
        const timedOut = String(err?.message ?? "").toLowerCase().includes("timeout");
        setError(timedOut ? "Backtesting is taking longer than expected. Try Run again or reduce the strategy set." : err?.message ?? "Backtesting engine is unavailable.");
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const selectedRun = useMemo(() => {
    return payload?.runs?.find((run) => run.strategy === selected) ?? bestRun(payload);
  }, [payload, selected]);
  const metrics = selectedRun?.metrics ?? {};
  const ranked = payload?.ranked ?? [];
  const curve = selectedRun?.equity_curve ?? [];

  return (
    <section className="dashboard-page">
      <div className="page-heading dashboard-heading">
        <div>
          <h1>Backtesting Engine</h1>
          <p>Strategy replay, performance metrics, equity curve, and comparison ranking.</p>
        </div>
        <div className="dashboard-actions">
          <span className="status-pill">{payload?.best_strategy ? `Best: ${titleCase(payload.best_strategy)}` : "Ready"}</span>
          <button className="refresh-button" type="button" onClick={() => load("full")} disabled={loading}>
            Run
          </button>
        </div>
      </div>

      {loading && <div className="alert" role="status">Running strategy comparison...</div>}
      {error && <div className="alert alert-error" role="alert">{error}</div>}

      {!loading && !error && (
        <>
          <div className="metric-grid">
            <article className="metric-card">
              <span className="metric-label">CAGR</span>
              <strong className="metric-value">{formatPercent(metrics.cagr)}</strong>
              <span className="metric-helper">Annualized return</span>
            </article>
            <article className="metric-card">
              <span className="metric-label">Win Rate</span>
              <strong className="metric-value">{formatPercent(metrics.win_rate_pct ?? number(metrics.win_rate) * 100)}</strong>
              <span className="metric-helper">{metrics.total_trades ?? 0} total trades</span>
            </article>
            <article className="metric-card">
              <span className="metric-label">Max Drawdown</span>
              <strong className="metric-value">{formatPercent(number(metrics.max_drawdown) * 100)}</strong>
              <span className="metric-helper">Peak-to-trough equity loss</span>
            </article>
            <article className="metric-card">
              <span className="metric-label">Sharpe Ratio</span>
              <strong className="metric-value">{formatNumber(metrics.sharpe_ratio)}</strong>
              <span className="metric-helper">Risk-adjusted replay return</span>
            </article>
            <article className="metric-card">
              <span className="metric-label">Profit Factor</span>
              <strong className="metric-value">{formatNumber(metrics.profit_factor)}</strong>
              <span className="metric-helper">Gross profit / gross loss</span>
            </article>
            <article className="metric-card">
              <span className="metric-label">Average P/L</span>
              <strong className="metric-value">{formatMoney(metrics.average_pnl)}</strong>
              <span className="metric-helper">Win {formatMoney(metrics.average_profit)} / Loss {formatMoney(metrics.average_loss)}</span>
            </article>
          </div>

          <section className="dashboard-section">
            <div className="section-header">
              <div>
                <h2>Strategy Comparison</h2>
                <span>{payload?.symbol ?? "NIFTY"} | Updated {payload?.updated_at ? new Date(payload.updated_at).toLocaleString() : "-"}</span>
              </div>
            </div>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Strategy</th>
                    <th>CAGR</th>
                    <th>Win Rate</th>
                    <th>Sharpe</th>
                    <th>Profit Factor</th>
                    <th>Max DD</th>
                    <th>Trades</th>
                    <th>Net P&L</th>
                  </tr>
                </thead>
                <tbody>
                  {ranked.map((run) => (
                    <tr key={run.strategy} onClick={() => setSelected(run.strategy)}>
                      <td>{titleCase(run.strategy)}</td>
                      <td>{formatPercent(run.metrics?.cagr)}</td>
                      <td>{formatPercent(run.metrics?.win_rate_pct ?? number(run.metrics?.win_rate) * 100)}</td>
                      <td>{formatNumber(run.metrics?.sharpe_ratio)}</td>
                      <td>{formatNumber(run.metrics?.profit_factor)}</td>
                      <td>{formatPercent(number(run.metrics?.max_drawdown) * 100)}</td>
                      <td>{run.metrics?.total_trades ?? 0}</td>
                      <td>{formatMoney(run.metrics?.net_pnl ?? run.metrics?.pnl)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="dashboard-section">
            <div className="form-panel signal-panel">
              <div className="form-panel-header">
                <div>
                  <h2>{selectedRun ? titleCase(selectedRun.strategy) : "Equity Curve"}</h2>
                  <p>Starting {formatMoney(metrics.starting_equity)} | Ending {formatMoney(metrics.ending_equity)}</p>
                </div>
                <span className="status-pill">{curve.length} points</span>
              </div>
              <div className="signal-trade-grid">
                {curve.slice(-8).map((point) => (
                  <span key={`${selectedRun?.strategy}-${point.index}`}>
                    <small>Point {point.index}</small>
                    <strong>{formatMoney(point.equity)}</strong>
                    <small>{point.time ? new Date(point.time).toLocaleTimeString() : "Start"}</small>
                  </span>
                ))}
              </div>
            </div>
          </section>
        </>
      )}
    </section>
  );
}
