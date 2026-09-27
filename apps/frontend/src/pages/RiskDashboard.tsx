import { useEffect, useState } from "react";
import { api } from "../api";

type ReadinessPayload = {
  passed?: boolean;
  min_sessions?: number;
  closed_trades?: number;
  cost_adjusted_trades?: number;
  session_count?: number;
  positive_session_count?: number;
  net_pnl?: number;
  total_costs?: number;
  net_expectancy?: number;
  blockers?: string[];
  source?: string;
  live_money_approval_required?: boolean;
};

type RiskPayload = {
  generated_at?: string;
  state?: string;
  pnl?: Record<string, number | string>;
  position_sizing?: {
    capital?: number;
    entry_price?: number;
    stop_loss?: number;
    fixed_risk?: { risk_amount?: number; risk_per_unit?: number; quantity?: number };
    atr_based?: { atr?: number | null; atr_multiplier?: number; risk_per_unit?: number; quantity?: number };
  };
  limits?: Record<string, number | string | null>;
  exposure?: { current?: number; limit?: number; available?: number; utilization_pct?: number };
  checks?: Record<string, boolean>;
  check_details?: Record<string, string>;
  positions?: {
    open_positions?: number;
    current_exposure?: number;
    realized_pnl?: number;
    unrealized_pnl?: number;
    open?: Array<Record<string, any>>;
  };
};

function money(value: unknown) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "-";
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(parsed);
}

function number(value: unknown, digits = 2) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed.toFixed(digits) : "-";
}

function checkClass(value?: boolean) {
  if (value === true) return "health-ok";
  if (value === false) return "health-fail";
  return "health-warn";
}

export default function RiskDashboard() {
  const [payload, setPayload] = useState<RiskPayload | null>(null);
  const [readiness, setReadiness] = useState<ReadinessPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    Promise.all([api.portfolioRiskDashboard(), api.realMoneyReadiness()])
      .then(([riskData, readinessData]) => {
        setPayload(riskData);
        setReadiness(readinessData);
        setError(null);
      })
      .catch((err) => setError(err?.message ?? "Risk dashboard is unavailable."))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const checks = payload?.checks ?? {};
  const checkDetails = payload?.check_details ?? {};
  const sizing = payload?.position_sizing;

  return (
    <section className="dashboard-page">
      <div className="page-heading dashboard-heading">
        <div>
          <h1>Portfolio Risk</h1>
          <p>Period P&L, position sizing, limits, exposure, and open risk.</p>
        </div>
        <div className="dashboard-actions">
          <span className={`status-pill${payload?.state === "blocked" ? " error" : ""}`}>{payload?.state ?? "Loading"}</span>
          <button className="refresh-button" type="button" onClick={load} disabled={loading}>
            Refresh
          </button>
        </div>
      </div>

      {loading && <div className="alert" role="status">Loading portfolio risk...</div>}
      {error && <div className="alert alert-error" role="alert">{error}</div>}

      {!loading && !error && (
        <>
          <div className="metric-grid">
            <article className="metric-card">
              <span className="metric-label">Daily P&L</span>
              <strong className="metric-value">{money(payload?.pnl?.daily)}</strong>
              <span className="metric-helper">Includes open unrealized P&L</span>
            </article>
            <article className="metric-card">
              <span className="metric-label">Weekly P&L</span>
              <strong className="metric-value">{money(payload?.pnl?.weekly)}</strong>
              <span className="metric-helper">{payload?.pnl?.basis ?? "portfolio basis"}</span>
            </article>
            <article className="metric-card">
              <span className="metric-label">Monthly P&L</span>
              <strong className="metric-value">{money(payload?.pnl?.monthly)}</strong>
              <span className="metric-helper">Rolling 30-day realized + open</span>
            </article>
            <article className="metric-card">
              <span className="metric-label">Exposure</span>
              <strong className="metric-value">{number(payload?.exposure?.utilization_pct)}%</strong>
              <span className="metric-helper">{money(payload?.exposure?.current)} / {money(payload?.exposure?.limit)}</span>
            </article>
            <article className="metric-card">
              <span className="metric-label">Open Trades</span>
              <strong className="metric-value">{payload?.limits?.open_trades ?? 0}/{payload?.limits?.max_open_trades ?? "-"}</strong>
              <span className="metric-helper">Max open trades</span>
            </article>
            <article className="metric-card">
              <span className="metric-label">Daily Loss Left</span>
              <strong className="metric-value">{money(payload?.limits?.daily_loss_remaining)}</strong>
              <span className="metric-helper">Limit {money(payload?.limits?.daily_loss_limit)}</span>
            </article>
          </div>

          <section className="dashboard-section">
            <div className="section-header">
              <div>
                <h2>Real-Money Evidence</h2>
                <span>Paper evidence only. Separate human approval is still required before any funded trading.</span>
              </div>
              <span className={`status-pill${readiness?.passed ? "" : " error"}`}>
                {readiness?.passed ? "Evidence threshold met" : "Not ready"}
              </span>
            </div>
            <div className="risk-summary-grid">
              <span>
                <small>Paper Sessions</small>
                <strong>{readiness?.session_count ?? 0}/{readiness?.min_sessions ?? 30}</strong>
                <small>{readiness?.positive_session_count ?? 0} positive sessions</small>
              </span>
              <span>
                <small>Cost-Adjusted Trades</small>
                <strong>{readiness?.cost_adjusted_trades ?? 0}</strong>
                <small>{readiness?.closed_trades ?? 0} closed trades</small>
              </span>
              <span>
                <small>Net Expectancy</small>
                <strong>{money(readiness?.net_expectancy)}</strong>
                <small>After recorded costs</small>
              </span>
              <span>
                <small>Total Costs</small>
                <strong>{money(readiness?.total_costs)}</strong>
                <small>Persisted paper evidence</small>
              </span>
            </div>
            {(readiness?.blockers?.length ?? 0) > 0 && (
              <div className="alert alert-error" role="status">
                {readiness?.blockers?.map((blocker) => blocker.replace(/_/g, " ")).join(" · ")}
              </div>
            )}
          </section>

          <section className="dashboard-section">
            <div className="section-header">
              <div>
                <h2>Position Sizing</h2>
                <span>Capital {money(sizing?.capital)} | Entry {number(sizing?.entry_price)} | Stop {number(sizing?.stop_loss)}</span>
              </div>
            </div>
            <div className="risk-summary-grid">
              <span>
                <small>Fixed Risk Quantity</small>
                <strong>{sizing?.fixed_risk?.quantity ?? 0}</strong>
                <small>Risk/unit {number(sizing?.fixed_risk?.risk_per_unit)}</small>
              </span>
              <span>
                <small>Fixed Risk Amount</small>
                <strong>{money(sizing?.fixed_risk?.risk_amount)}</strong>
                <small>{payload?.limits?.risk_per_trade_pct ?? "-"}% per trade</small>
              </span>
              <span>
                <small>ATR Quantity</small>
                <strong>{sizing?.atr_based?.quantity ?? 0}</strong>
                <small>ATR {number(sizing?.atr_based?.atr)}</small>
              </span>
              <span>
                <small>ATR Risk/Unit</small>
                <strong>{number(sizing?.atr_based?.risk_per_unit)}</strong>
                <small>{sizing?.atr_based?.atr_multiplier ?? "-"}x ATR</small>
              </span>
            </div>
          </section>

          <section className="dashboard-section">
            <div className="health-dot-grid">
              {Object.entries(checks).map(([key, value]) => (
                <span key={key} className={checkClass(value)} title={!value ? checkDetails[key] : undefined}>
                  <strong>{key.replace(/_/g, " ")}</strong>
                  <small>{value ? "OK" : checkDetails[key] ? "Blocked - hover for why" : "Blocked"}</small>
                </span>
              ))}
            </div>
          </section>

          <section className="dashboard-section">
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Qty</th>
                    <th>Entry</th>
                    <th>Current</th>
                    <th>Open P&L</th>
                  </tr>
                </thead>
                <tbody>
                  {(payload?.positions?.open ?? []).map((position) => (
                    <tr key={position.id ?? `${position.symbol}-${position.opened_at}`}>
                      <td>{position.symbol}</td>
                      <td>{position.side}</td>
                      <td>{position.quantity}</td>
                      <td>{number(position.entry_price)}</td>
                      <td>{number(position.current_price)}</td>
                      <td>{money(position.open_pnl)}</td>
                    </tr>
                  ))}
                  {(payload?.positions?.open ?? []).length === 0 && (
                    <tr>
                      <td colSpan={6}>No open positions.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </section>
  );
}
