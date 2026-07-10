import { useEffect, useMemo, useRef, useState } from "react";
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

type BacktestJob = {
  job_id: string;
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED" | "TIMEOUT";
  message?: string;
  updated_at?: string;
  current_strategy?: string | null;
  completed_strategies: number;
  total_strategies: number;
  progress_pct: number;
  elapsed_seconds: number;
  estimated_remaining_seconds?: number | null;
  partial_results?: BacktestRun[];
  result?: BacktestComparison | null;
  error?: string | null;
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

function formatDuration(seconds: unknown) {
  const parsed = Number(seconds);
  if (!Number.isFinite(parsed)) return "calculating";
  const total = Math.max(0, Math.round(parsed));
  const minutes = Math.floor(total / 60);
  const remainder = total % 60;
  return minutes ? `${minutes}m ${remainder}s` : `${remainder}s`;
}

function backtestRankScore(run: BacktestRun) {
  const hasTrades = number(run.metrics?.total_trades) > 0 ? 1 : 0;
  return hasTrades * 1_000_000_000
    + number(run.metrics?.sharpe_ratio) * 100_000
    + number(run.metrics?.net_pnl ?? run.metrics?.pnl)
    - number(run.metrics?.max_drawdown) * 1_000;
}

function jobPayload(job: BacktestJob | null): BacktestComparison | null {
  if (!job) return null;
  if (job.result) return job.result;
  const runs = job.partial_results ?? [];
  if (!runs.length) return null;
  const ranked = [...runs].sort((left, right) => backtestRankScore(right) - backtestRankScore(left));
  return {
    module: "backtesting_comparison",
    symbol: "NIFTY",
    runs,
    ranked,
    best_strategy: ranked[0]?.strategy ?? null,
    updated_at: job.updated_at,
  } as BacktestComparison;
}

function isActiveJob(job: BacktestJob | null) {
  return Boolean(job && ["QUEUED", "RUNNING", "TIMEOUT"].includes(job.status));
}

function progressLabel(job: BacktestJob | null) {
  if (!job) return "Ready";
  if (job.status === "COMPLETED") return "Completed";
  if (job.status === "CANCELLED") return "Cancelled";
  if (job.status === "FAILED") return "Failed";
  if (job.status === "TIMEOUT") return "Long Running";
  if (job.status === "QUEUED") return "Queued";
  return "Running";
}

function strategyLabel(job: BacktestJob | null) {
  if (!job) return "-";
  if (job.status === "COMPLETED") return "All strategies completed";
  if (job.status === "FAILED") return "Stopped on error";
  if (job.status === "CANCELLED") return "Cancelled";
  if (job.current_strategy) return titleCase(job.current_strategy);
  return "Waiting to start";
}

export default function Backtesting() {
  const [payload, setPayload] = useState<BacktestComparison | null>(null);
  const [job, setJob] = useState<BacktestJob | null>(null);
  const [selected, setSelected] = useState("amd");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  const load = (mode: "quick" | "full" = "quick") => {
    setLoading(true);
    setError(null);
    const strategies = mode === "full" ? defaultStrategies : quickStrategies;
    api.startBacktest({ symbol: "NIFTY", strategies, min_score: 0, max_candles: mode === "full" ? 120 : 80 })
      .then((data: BacktestJob) => {
        setJob(data);
        setPayload(jobPayload(data));
        setSelected("amd");
        setError(null);
      })
      .catch((err) => {
        setError(err?.response?.data?.detail ?? err?.message ?? "Backtesting engine is unavailable.");
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, []);

  useEffect(() => {
    if (!job?.job_id || ["COMPLETED", "FAILED", "CANCELLED"].includes(job.status)) {
      if (pollRef.current) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return;
    }
    if (pollRef.current) return;
    pollRef.current = window.setInterval(() => {
      api.backtestJob(job.job_id)
        .then((data: BacktestJob) => {
          setJob(data);
          const nextPayload = jobPayload(data);
          if (nextPayload) {
            setPayload(nextPayload);
            setSelected((current) => nextPayload.runs?.some((run) => run.strategy === current) ? current : nextPayload.best_strategy ?? nextPayload.runs?.[0]?.strategy ?? "amd");
          }
          if (data.status === "FAILED") {
            setError(data.message ?? "Backtest failed.");
          }
        })
        .catch((err: any) => {
          setError(err?.response?.data?.detail ?? err?.message ?? "Backtest status is unavailable.");
        });
    }, 1500);
  }, [job?.job_id, job?.status]);

  const cancelJob = () => {
    if (!job?.job_id) return;
    api.cancelBacktest(job.job_id).then((data: BacktestJob) => setJob(data));
  };

  const refreshJob = () => {
    if (!job?.job_id) return;
    api.backtestJob(job.job_id).then((data: BacktestJob) => {
      setJob(data);
      const nextPayload = jobPayload(data);
      if (nextPayload) setPayload(nextPayload);
    });
  };

  const selectedRun = useMemo(() => {
    return payload?.runs?.find((run) => run.strategy === selected) ?? bestRun(payload);
  }, [payload, selected]);
  const metrics = selectedRun?.metrics ?? {};
  const ranked = payload?.ranked ?? [];
  const curve = selectedRun?.equity_curve ?? [];
  const active = isActiveJob(job);
  const progress = Math.max(0, Math.min(100, Number(job?.progress_pct ?? 0)));
  const currentStrategy = strategyLabel(job);
  const statusLabel = progressLabel(job);

  return (
    <section className="dashboard-page">
      <div className="page-heading dashboard-heading">
        <div>
          <h1>Backtesting Engine</h1>
          <p>Strategy replay, performance metrics, equity curve, and comparison ranking.</p>
        </div>
        <div className="dashboard-actions">
          <span className={`status-pill ${job?.status === "FAILED" ? "error" : job?.status === "TIMEOUT" ? "stale" : ""}`}>
            {job?.status ?? (payload?.best_strategy ? `Best: ${titleCase(payload.best_strategy)}` : "Ready")}
          </span>
          <button className="refresh-button" type="button" onClick={() => load("full")} disabled={loading || Boolean(active)}>
            Run
          </button>
        </div>
      </div>

      {loading && <div className="alert" role="status">Backtest has been queued and will start shortly.</div>}
      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {job && !error && (
        <div className={job.status === "TIMEOUT" ? "alert alert-warning" : job.status === "COMPLETED" ? "alert alert-success" : "alert"} role="status">
          {job.message}
        </div>
      )}

      {job && (
        <section className="dashboard-section">
          <div className="form-panel">
            <div className="form-panel-header">
              <div>
                <h2>Backtest Progress</h2>
                <p>{currentStrategy} ({job.completed_strategies}/{job.total_strategies})</p>
              </div>
              <div className="dashboard-actions">
                <button className="refresh-button" type="button" onClick={refreshJob}>Refresh results</button>
                {active && <button className="refresh-button" type="button" onClick={cancelJob}>Cancel</button>}
              </div>
            </div>
            <div className="backtest-progress-track" aria-label={`Backtest progress ${progress}%`}>
              <span style={{ width: `${progress}%` }} />
            </div>
            <div className="signal-trade-grid">
              <span>
                <small>Status</small>
                <strong>{formatNumber(progress, 0)}%</strong>
                <small>{statusLabel}</small>
              </span>
              <span>
                <small>Strategy</small>
                <strong>{currentStrategy}</strong>
                <small>{job.completed_strategies}/{job.total_strategies}</small>
              </span>
              <span>
                <small>Elapsed</small>
                <strong>{formatDuration(job.elapsed_seconds)}</strong>
                <small>Background job</small>
              </span>
              <span>
                <small>Remaining</small>
                <strong>{formatDuration(job.estimated_remaining_seconds)}</strong>
                <small>Estimated</small>
              </span>
            </div>
          </div>
        </section>
      )}

      {!loading && !error && payload && (
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


