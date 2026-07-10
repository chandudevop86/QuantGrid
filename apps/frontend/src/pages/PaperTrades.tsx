import { useEffect, useState } from "react";
import { api } from "../api";
import Loader from "../components/Loader";

function money(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number)
    ? number.toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 })
    : "-";
}

function rowsFrom(payload: any) {
  if (Array.isArray(payload)) return payload;
  return payload?.rows ?? payload?.trades ?? payload?.positions ?? [];
}

export default function PaperTrades() {
  const [trades, setTrades] = useState<any[]>([]);
  const [positions, setPositions] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const [tradePayload, positionPayload, summaryPayload] = await Promise.all([
        api.paperTrades(), api.openPositions(), api.positionSummary(),
      ]);
      setTrades(rowsFrom(tradePayload));
      setPositions(rowsFrom(positionPayload));
      setSummary(summaryPayload ?? {});
      setError(null);
    } catch (reason: any) {
      setError(reason?.response?.data?.detail ?? reason?.message ?? "Paper trading data is unavailable.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  return (
    <section className="dashboard-page">
      <div className="page-heading dashboard-heading">
        <div><span className="page-eyebrow">Paper execution</span><h1>Trades & positions</h1><p>Monitor simulated orders, open exposure, and recent outcomes without risking capital.</p></div>
        <button className="refresh-button" type="button" onClick={() => void load()} disabled={loading}>Refresh</button>
      </div>
      {loading && <Loader label="Loading paper portfolio..." />}
      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {!loading && !error && <>
        <div className="metric-grid">
          <article className="metric-card"><span className="metric-label">Open Positions</span><strong className="metric-value">{summary.open_positions ?? positions.length}</strong><span className="metric-helper">Currently monitored</span></article>
          <article className="metric-card"><span className="metric-label">Current Exposure</span><strong className="metric-value">{money(summary.current_exposure)}</strong><span className="metric-helper">Simulated notional</span></article>
          <article className="metric-card"><span className="metric-label">Realized P&amp;L</span><strong className="metric-value">{money(summary.realized_pnl)}</strong><span className="metric-helper">Closed paper positions</span></article>
        </div>
        <section className="dashboard-section"><div className="section-header"><h2>Open positions</h2><span>{positions.length} active</span></div><div className="table-wrap"><table className="table"><thead><tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Entry</th><th>Current</th><th>Stop</th><th>Target</th><th>Open P&amp;L</th><th>Status</th></tr></thead><tbody>
          {positions.map((row) => <tr key={row.id ?? row.broker_order_id}><td>{row.symbol ?? "-"}</td><td>{row.side ?? "-"}</td><td>{row.quantity ?? "-"}</td><td>{row.entry_price ?? "-"}</td><td>{row.current_price ?? "-"}</td><td>{row.stop_loss ?? "-"}</td><td>{row.target ?? "-"}</td><td>{money(row.open_pnl)}</td><td><span className="status-pill">{row.status ?? "open"}</span></td></tr>)}
          {!positions.length && <tr><td colSpan={9} className="empty-table-cell"><strong>No open paper positions</strong><span>New simulated positions will appear here after execution.</span></td></tr>}
        </tbody></table></div></section>
        <section className="dashboard-section"><div className="section-header"><h2>Recent paper orders</h2><span>{trades.length} records</span></div><div className="table-wrap"><table className="table"><thead><tr><th>Created</th><th>Strategy</th><th>Symbol</th><th>Side</th><th>Entry</th><th>Stop</th><th>Target</th><th>P&amp;L</th><th>Status</th></tr></thead><tbody>
          {trades.slice(0, 25).map((row) => <tr key={row.id ?? row.broker_order_id}><td>{row.created_at ? new Date(row.created_at).toLocaleString() : "-"}</td><td>{row.strategy ?? "-"}</td><td>{row.symbol ?? "-"}</td><td>{row.side ?? "-"}</td><td>{row.entry ?? row.entry_price ?? "-"}</td><td>{row.stop_loss ?? "-"}</td><td>{row.target ?? "-"}</td><td>{money(row.pnl)}</td><td><span className="status-pill">{row.status ?? "-"}</span></td></tr>)}
          {!trades.length && <tr><td colSpan={9} className="empty-table-cell"><strong>No paper orders yet</strong><span>Orders placed in Paper Mode will be recorded here.</span></td></tr>}
        </tbody></table></div></section>
      </>}
    </section>
  );
}
