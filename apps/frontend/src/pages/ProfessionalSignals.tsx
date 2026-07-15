import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
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

function emptyBacktest(message = "Backtest has been queued and will start shortly.") {
  return {
    metrics: { total_trades: 0, win_rate: 0, pnl: 0, sharpe_ratio: 0 },
    equity_curve: [],
    job_status: "QUEUED",
    job_message: message,
    progress_pct: 0,
  };
}

function backtestFromJob(job: any) {
  const run = job?.result?.runs?.[0] ?? job?.partial_results?.[0] ?? {};
  return {
    ...run,
    metrics: run?.metrics ?? { total_trades: 0, win_rate: 0, pnl: 0, sharpe_ratio: 0 },
    equity_curve: run?.equity_curve ?? [],
    job_status: job?.status,
    job_message: job?.message,
    progress_pct: job?.progress_pct ?? 0,
  };
}

function isBacktestActive(job: any) {
  return ["QUEUED", "RUNNING", "TIMEOUT"].includes(String(job?.status ?? ""));
}

export default function ProfessionalSignals() {
  const [signals, setSignals] = useState<any>(null);
  const [trades, setTrades] = useState<any[]>([]);
  const [risk, setRisk] = useState<any>(null);
  const [backtest, setBacktest] = useState<any>(null);
  const [journal, setJournal] = useState<any>(null);
  const [audit, setAudit] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [partialErrors, setPartialErrors] = useState<string[]>([]);
  const developerMode = useUiMode() === "developer";

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setBacktest(emptyBacktest());
    const calls: Array<[string, Promise<any>]> = [
      ["signals", api.latestSignals()],
      ["trade journal", api.tradeJournal()],
      ["risk engine", api.riskEngine()],
      ["signal audit", api.signalsAudit()],
    ];
    Promise.allSettled(calls.map(([, promise]) => promise))
      .then(([signalResult, journalResult, riskResult, auditResult]) => {
        if (cancelled) return;
        // Track WHICH calls failed and why, instead of silently discarding the reason. A
        // fallback "no data" object looks identical in the UI whether the backend legitimately
        // has nothing to report or the request actually errored (401/500/network failure) --
        // previously that distinction was invisible without opening browser devtools.
        const failures: string[] = [];
        [signalResult, journalResult, riskResult, auditResult].forEach((result, index) => {
          if (result.status === "rejected") {
            const [label] = calls[index];
            const reason = result.reason?.response?.status
              ? `HTTP ${result.reason.response.status}`
              : result.reason?.message || "request failed";
            failures.push(`${label} (${reason})`);
          }
        });
        if (failures.length === calls.length) {
          setError("Signal dashboard is unavailable.");
          setPartialErrors([]);
        } else {
          setError(null);
          setPartialErrors((prev) => {
            const merged = [...failures];
            for (const item of prev) {
              if (item.startsWith("backtest ") && !merged.includes(item)) merged.push(item);
            }
            return merged;
          });
        }

        const signalData = signalResult.status === "fulfilled" ? signalResult.value : { active_signals: [], rejected_signals: [], stale_signals: [], message: "Signals unavailable." };
        const journalData = journalResult.status === "fulfilled" ? journalResult.value : { recent_trades: [], total_trades: 0, win_rate: 0, pnl: 0 };
        const riskData = riskResult.status === "fulfilled" ? riskResult.value : { summary: { trades_today: 0, daily_pnl: 0 } };
        const auditData = auditResult.status === "fulfilled" ? auditResult.value : { strategies: [], lifecycle_totals: {} };
        setSignals(signalData);
        setJournal(journalData);
        setTrades(Array.isArray(journalData?.recent_trades) ? journalData.recent_trades : []);
        setRisk(riskData?.summary ?? riskData);
        setAudit(auditData);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    api.startBacktest({ symbol: "NIFTY", strategies: [backtestStrategy], min_score: 0, expected_seconds: 45 })
      .then(function poll(job: any): any {
        if (cancelled) return null;
        setBacktest(backtestFromJob(job));
        if (!isBacktestActive(job)) return job;
        return new Promise((resolve) => window.setTimeout(resolve, 2500))
          .then(() => api.backtestJob(job.job_id))
          .then(poll);
      })
      .catch((reason) => {
        if (cancelled) return;
        const detail = reason?.response?.status ? `HTTP ${reason.response.status}` : reason?.message || "request failed";
        setPartialErrors((items) => [...items, `backtest (${detail})`]);
        setBacktest(emptyBacktest("Backtest is unavailable right now."));
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="dashboard-page">
      <div className="page-heading">
        <h1>Signals</h1>
        <p>Active, rejected, stale, risk, journal, and backtest view.</p>
      </div>

      {loading && <Loader label="Loading signal dashboard..." />}
      {error && <div className="alert alert-error">{error}</div>}
      {!loading && !error && partialErrors.length > 0 && (
        <div className="alert alert-warning">
          Some data failed to load and is showing as empty/unavailable below: {partialErrors.join(", ")}.
        </div>
      )}

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
              <h2>Signal Audit</h2>
              <span>{audit?.latest_candle_time ?? signals?.latest_candle_time ?? "-"}</span>
            </div>
            <div className="signal-audit-summary">
              {["RAW_SIGNAL", "VALIDATED_SIGNAL", "ACCEPTED_SIGNAL", "REJECTED_SIGNAL", "PAPER_TRADE_CREATED"].map((key) => (
                <span key={key}>
                  <small>{key.replace(/_/g, " ")}</small>
                  <strong>{audit?.lifecycle_totals?.[key] ?? 0}</strong>
                </span>
              ))}
            </div>
            <div className="table-wrap">
              <table className="table signal-audit-table">
                <thead>
                  <tr>
                    <th>Strategy</th>
                    <th>Raw</th>
                    <th>Validated</th>
                    <th>Rejected</th>
                    <th>Latest</th>
                    <th>Confidence</th>
                    <th>RR</th>
                    <th>No Trade Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {(audit?.strategies ?? []).map((row: any) => (
                    <tr key={row.strategy_key ?? row.strategy}>
                      <td>{row.strategy}</td>
                      <td>{row.raw_signal_count ?? 0}</td>
                      <td>{row.validated_signal_count ?? 0}</td>
                      <td>{row.rejected_signal_count ?? 0}</td>
                      <td>{row.latest_signal ?? "NEUTRAL"}</td>
                      <td>{row.confidence == null ? "-" : `${row.confidence}%`}</td>
                      <td>{row.risk_reward ?? "-"}</td>
                      <td>{row.rejection_reason ?? row.execution_decision ?? "READY_FOR_PAPER_TRADE"}</td>
                    </tr>
                  ))}
                  {(!audit?.strategies || audit.strategies.length === 0) && (
                    <tr>
                      <td colSpan={8}>Signal audit is unavailable.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            {developerMode && (
              <details className="technical-details">
                <summary>Signal Audit API Payload</summary>
                <pre>{JSON.stringify(localizeTimestamps(audit ?? {}), null, 2)}</pre>
              </details>
            )}
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
                  {[
                    ...(signals?.active_signals ?? []),
                    ...(signals?.rejected_signals ?? []),
                    ...(signals?.stale_signals ?? []),
                  ].length === 0 && (
                    <tr>
                      <td colSpan={5}>{signals?.message ?? "No signals available yet."}</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="strategy-signal-grid">
            <div className="form-panel signal-panel">
              <div className="form-panel-header">
                <div>
                  <h2>Backtest Validation</h2>
                  <p>{backtest?.job_message ?? `${backtestStrategy.toUpperCase()} / NIFTY / 1m`}</p>
                </div>
                <span className="status-pill">{backtest?.job_status ?? "QUEUED"} {Math.round(Number(backtest?.progress_pct ?? 0))}%</span>
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
              <div className="dashboard-actions">
                <Link className="refresh-button" to="/history">Open full backtest results</Link>
              </div>
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
