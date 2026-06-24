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

  useEffect(() => {
    let isMounted = true;
    const load = () => {
      api.tradeJournalRows()
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
  }, []);

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
              <h2>Journal Entries</h2>
              <span>{rows.length} rows</span>
            </div>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Strategy</th>
                    <th>Signal</th>
                    <th>Entry</th>
                    <th>Stop</th>
                    <th>Target</th>
                    <th>Exit</th>
                    <th>PnL</th>
                    <th>Exit Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row: any) => (
                    <tr key={`${row.id}-${row.created_at}`}>
                      <td>{formatDate(row.created_at)}</td>
                      <td>{row.strategy ?? "-"}</td>
                      <td>{row.signal ?? "-"}</td>
                      <td>{row.entry ?? "-"}</td>
                      <td>{row.stop_loss ?? "-"}</td>
                      <td>{row.target ?? "-"}</td>
                      <td>{row.exit_price ?? "-"}</td>
                      <td>{formatMoney(row.pnl)}</td>
                      <td>{row.exit_reason ?? "-"}</td>
                    </tr>
                  ))}
                  {rows.length === 0 && (
                    <tr>
                      <td colSpan={9}>No trade journal entries recorded yet.</td>
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
