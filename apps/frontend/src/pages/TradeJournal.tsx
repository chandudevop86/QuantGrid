import { useEffect, useState } from "react";
import { api } from "../api";
import Loader from "../components/Loader";

function formatMoney(value: unknown) {
  const numeric = Number(value);
  return Number.isFinite(numeric)
    ? numeric.toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 })
    : "-";
}

function formatDate(value: unknown) {
  return value ? new Date(String(value)).toLocaleString() : "-";
}

export default function TradeJournal() {
  const [payload, setPayload] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState({ strategy: "", status: "", date: "", symbol: "" });

  useEffect(() => {
    let isMounted = true;
    const load = () => {
      const params = Object.fromEntries(Object.entries(filters).filter(([, value]) => value));
      api.tradeJournalRows(params)
        .then((data) => {
          if (!isMounted) return;
          setPayload(data);
          setError(null);
        })
        .catch(() => {
          if (isMounted) setError("Trade journal API is not available.");
        });
    };
    load();
    const id = window.setInterval(load, 30000);
    return () => {
      isMounted = false;
      window.clearInterval(id);
    };
  }, [filters]);

  const rows = Array.isArray(payload?.rows) ? payload.rows : [];
  const summary = payload?.summary ?? {};

  return (
    <section className="dashboard-page">
      <div className="page-heading">
        <h1>Trade Journal</h1>
        <p>Strategy signals, entries, exits, PnL, and exit reasons.</p>
      </div>

      {!payload && !error && <Loader label="Loading trade journal..." />}
      {error && <div className="alert alert-error" role="alert">{error}</div>}

      {payload && (
        <>
          <div className="metric-grid">
            <div className="metric-card">
              <span className="metric-label">Total Trades</span>
              <strong className="metric-value">{summary.total_trades ?? rows.length}</strong>
              <span className="metric-helper">Journal rows</span>
            </div>
            <div className="metric-card">
              <span className="metric-label">Closed Trades</span>
              <strong className="metric-value">{summary.closed_trades ?? 0}</strong>
              <span className="metric-helper">Exited or closed</span>
            </div>
            <div className="metric-card">
              <span className="metric-label">Win Rate</span>
              <strong className="metric-value">{Number(summary.win_rate ?? 0).toFixed(1)}%</strong>
              <span className="metric-helper">Closed trades only</span>
            </div>
            <div className="metric-card">
              <span className="metric-label">PnL</span>
              <strong className="metric-value">{formatMoney(summary.pnl)}</strong>
              <span className="metric-helper">Realized journal PnL</span>
            </div>
          </div>

          <div className="dashboard-section">
            <div className="section-header">
              <h2>Filters</h2>
              <span>Trace signal to P&L</span>
            </div>
            <div className="field-grid">
              <label>
                <span>Strategy</span>
                <input value={filters.strategy} onChange={(event) => setFilters({ ...filters, strategy: event.target.value })} placeholder="breakout" />
              </label>
              <label>
                <span>Status</span>
                <input value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })} placeholder="accepted_signal" />
              </label>
              <label>
                <span>Date</span>
                <input value={filters.date} onChange={(event) => setFilters({ ...filters, date: event.target.value })} type="date" />
              </label>
              <label>
                <span>Symbol</span>
                <input value={filters.symbol} onChange={(event) => setFilters({ ...filters, symbol: event.target.value.toUpperCase() })} placeholder="NIFTY" />
              </label>
            </div>
          </div>

          <div className="dashboard-section">
            <div className="section-header">
              <h2>Journal Entries</h2>
              <span>{rows.length} rows</span>
            </div>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Strategy</th>
                    <th>Symbol</th>
                    <th>Signal</th>
                    <th>Status</th>
                    <th>Entry</th>
                    <th>Stop</th>
                    <th>Target</th>
                    <th>Qty</th>
                    <th>Exit</th>
                    <th>PnL</th>
                    <th>Reason</th>
                    <th>Exit Reason</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row: any) => (
                    <tr key={`${row.id}-${row.created_at}`}>
                      <td>{formatDate(row.timestamp ?? row.created_at)}</td>
                      <td>{row.strategy ?? "-"}</td>
                      <td>{row.symbol ?? "-"}</td>
                      <td>{row.signal ?? "-"}</td>
                      <td>{row.status ?? "-"}</td>
                      <td>{row.entry_price ?? row.entry ?? "-"}</td>
                      <td>{row.stop_loss ?? "-"}</td>
                      <td>{row.target ?? "-"}</td>
                      <td>{row.quantity ?? "-"}</td>
                      <td>{row.exit_price ?? "-"}</td>
                      <td>{formatMoney(row.pnl)}</td>
                      <td>{row.reason ?? "-"}</td>
                      <td>{row.exit_reason ?? "-"}</td>
                      <td>{row.source ?? "-"}</td>
                    </tr>
                  ))}
                  {rows.length === 0 && (
                    <tr>
                      <td colSpan={13}>No trade journal entries recorded yet.</td>
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
