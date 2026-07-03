import { useEffect, useState } from "react";
import { api } from "../api";

type EnginePayload = {
  state?: string;
  capabilities?: Record<string, boolean | string>;
  guardrails?: Record<string, boolean | string | null>;
  summary?: Record<string, number>;
  open_positions?: Array<Record<string, any>>;
  paper_execution_logs?: Array<Record<string, any>>;
  kill_switch?: { active?: boolean; reason?: string | null };
};

const defaultLeg = {
  strategy: "manual_basket",
  symbol: "NIFTY",
  side: "BUY",
  quantity: 1,
  entry: 24350,
  stop_loss: 24250,
  target: 24550,
  trailing_stop_pct: 0,
};

function number(value: unknown, digits = 2) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed.toFixed(digits) : "-";
}

function money(value: unknown) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "-";
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(parsed);
}

function text(value: unknown) {
  if (value === true) return "OK";
  if (value === false) return "Blocked";
  if (value == null || value === "") return "-";
  return String(value).replace(/_/g, " ");
}

export default function TradingEngine() {
  const [payload, setPayload] = useState<EnginePayload | null>(null);
  const [leg, setLeg] = useState(defaultLeg);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    api.tradingEngineDashboard()
      .then((data) => {
        setPayload(data);
        setError(null);
      })
      .catch((err) => setError(err?.response?.data?.detail ?? err?.message ?? "Trading engine is unavailable."))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const submitBasket = () => {
    setBusy(true);
    setMessage(null);
    api.paperBasketOrder({ execution_mode: "paper", reason: "manual command center basket", legs: [leg] })
      .then((result) => {
        setMessage(`${result.status}: ${result.created_count} leg created`);
        load();
      })
      .catch((err) => setError(err?.response?.data?.detail ?? err?.message ?? "Basket order failed."))
      .finally(() => setBusy(false));
  };

  const scale = (positionId: number, action: "scale_in" | "scale_out") => {
    setBusy(true);
    setMessage(null);
    api.scalePosition(positionId, { execution_mode: "paper", action, quantity: 1, reason: `manual ${action}` })
      .then((result) => {
        setMessage(`${result.status}: position ${positionId} is now ${result.new_quantity}`);
        load();
      })
      .catch((err) => setError(err?.response?.data?.detail ?? err?.message ?? "Scale action failed."))
      .finally(() => setBusy(false));
  };

  const positions = payload?.open_positions ?? [];
  const logs = payload?.paper_execution_logs ?? [];
  const capabilities = payload?.capabilities ?? {};
  const guardrails = payload?.guardrails ?? {};

  return (
    <section className="dashboard-page">
      <div className="page-heading dashboard-heading">
        <div>
          <h1>Trading Engine</h1>
          <p>Paper-first order controls, exits, scale actions, basket execution, logs, and guardrails.</p>
        </div>
        <div className="dashboard-actions">
          <span className={`status-pill${payload?.kill_switch?.active ? " error" : ""}`}>{payload?.state ?? "Loading"}</span>
          <button className="refresh-button" type="button" onClick={load} disabled={loading || busy}>
            Refresh
          </button>
        </div>
      </div>

      {loading && <div className="alert" role="status">Loading trading engine...</div>}
      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {message && <div className="alert alert-success" role="status">{message}</div>}

      {!loading && (
        <>
          <div className="metric-grid">
            <article className="metric-card">
              <span className="metric-label">Open Positions</span>
              <strong className="metric-value">{payload?.summary?.open_positions ?? 0}</strong>
              <span className="metric-helper">Exposure {money(payload?.summary?.current_exposure)}</span>
            </article>
            <article className="metric-card">
              <span className="metric-label">Unrealized P&L</span>
              <strong className="metric-value">{money(payload?.summary?.unrealized_pnl)}</strong>
              <span className="metric-helper">Today {money(payload?.summary?.todays_pnl)}</span>
            </article>
            <article className="metric-card">
              <span className="metric-label">Kill Switch</span>
              <strong className="metric-value">{payload?.kill_switch?.active ? "ACTIVE" : "Clear"}</strong>
              <span className="metric-helper">{payload?.kill_switch?.reason ?? "Paper workflows allowed"}</span>
            </article>
            <article className="metric-card">
              <span className="metric-label">Paper Logs</span>
              <strong className="metric-value">{logs.length}</strong>
              <span className="metric-helper">Recent executions</span>
            </article>
          </div>

          <section className="dashboard-section">
            <div className="section-header">
              <div>
                <h2>Guardrails</h2>
                <span>Live basket and scale workflows stay blocked until broker confirmations are built.</span>
              </div>
            </div>
            <div className="health-dot-grid">
              {Object.entries({ ...capabilities, ...guardrails }).map(([key, value]) => (
                <span key={key} className={value === false ? "health-fail" : "health-ok"}>
                  <strong>{key.replace(/_/g, " ")}</strong>
                  <small>{text(value)}</small>
                </span>
              ))}
            </div>
          </section>

          <section className="dashboard-section">
            <div className="section-header">
              <div>
                <h2>Paper Basket</h2>
                <span>One-leg basket entry with stop, target, and optional trailing stop percent.</span>
              </div>
              <button className="refresh-button" type="button" onClick={submitBasket} disabled={busy}>
                Submit Paper Basket
              </button>
            </div>
            <div className="form-grid">
              <label>
                <span>Symbol</span>
                <input value={leg.symbol} onChange={(event) => setLeg({ ...leg, symbol: event.target.value.toUpperCase() })} />
              </label>
              <label>
                <span>Side</span>
                <select value={leg.side} onChange={(event) => setLeg({ ...leg, side: event.target.value })}>
                  <option value="BUY">BUY</option>
                  <option value="SELL">SELL</option>
                </select>
              </label>
              <label>
                <span>Qty</span>
                <input type="number" min="1" value={leg.quantity} onChange={(event) => setLeg({ ...leg, quantity: Number(event.target.value) })} />
              </label>
              <label>
                <span>Entry</span>
                <input type="number" value={leg.entry} onChange={(event) => setLeg({ ...leg, entry: Number(event.target.value) })} />
              </label>
              <label>
                <span>Stop Loss</span>
                <input type="number" value={leg.stop_loss} onChange={(event) => setLeg({ ...leg, stop_loss: Number(event.target.value) })} />
              </label>
              <label>
                <span>Target</span>
                <input type="number" value={leg.target} onChange={(event) => setLeg({ ...leg, target: Number(event.target.value) })} />
              </label>
              <label>
                <span>Trailing %</span>
                <input type="number" min="0" value={leg.trailing_stop_pct} onChange={(event) => setLeg({ ...leg, trailing_stop_pct: Number(event.target.value) })} />
              </label>
            </div>
          </section>

          <section className="dashboard-section">
            <div className="section-header">
              <div>
                <h2>Open Positions</h2>
                <span>Scale actions are paper-only and write execution logs.</span>
              </div>
            </div>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Qty</th>
                    <th>Entry</th>
                    <th>Stop</th>
                    <th>Target</th>
                    <th>TSL</th>
                    <th>P&L</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((position) => (
                    <tr key={position.id}>
                      <td>{position.symbol}</td>
                      <td>{position.side}</td>
                      <td>{position.quantity}</td>
                      <td>{number(position.entry_price)}</td>
                      <td>{number(position.stop_loss)}</td>
                      <td>{number(position.target)}</td>
                      <td>{number(position.trailing_stop_loss ?? position.trailing_stop_pct)}</td>
                      <td>{money(position.open_pnl)}</td>
                      <td>
                        <div className="table-actions">
                          <button type="button" onClick={() => scale(Number(position.id), "scale_in")} disabled={busy}>Scale In</button>
                          <button type="button" onClick={() => scale(Number(position.id), "scale_out")} disabled={busy}>Scale Out</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {positions.length === 0 && (
                    <tr>
                      <td colSpan={9}>No open positions.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section className="dashboard-section">
            <div className="section-header">
              <div>
                <h2>Paper Execution Logs</h2>
                <span>Recent paper orders, basket legs, and scale records.</span>
              </div>
            </div>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Created</th>
                    <th>Strategy</th>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Status</th>
                    <th>Entry</th>
                    <th>P&L</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.slice(0, 12).map((row) => (
                    <tr key={row.id}>
                      <td>{row.created_at ?? "-"}</td>
                      <td>{row.strategy}</td>
                      <td>{row.symbol}</td>
                      <td>{row.side}</td>
                      <td>{row.status}</td>
                      <td>{number(row.entry)}</td>
                      <td>{money(row.pnl)}</td>
                    </tr>
                  ))}
                  {logs.length === 0 && (
                    <tr>
                      <td colSpan={7}>No paper execution logs yet.</td>
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
