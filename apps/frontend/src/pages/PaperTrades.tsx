import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import Loader from "../components/Loader";
import { getCurrentMode, type TradingMode } from "../mode";

function money(value: unknown, digits = 2) {
  const number = Number(value);
  return Number.isFinite(number)
    ? number.toLocaleString("en-IN", { style: "currency", currency: "INR", minimumFractionDigits: digits, maximumFractionDigits: digits })
    : "-";
}

function number(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : "-";
}

function rowsFrom(payload: any) {
  if (Array.isArray(payload)) return payload;
  return payload?.rows ?? payload?.trades ?? payload?.positions ?? [];
}

function positionPnl(row: any, closed = false) {
  return Number(closed ? row.closed_pnl ?? row.pnl : row.open_pnl ?? row.pnl) || 0;
}

function positionChange(row: any, closed = false) {
  const entry = Number(row.entry_price ?? row.entry);
  const quantity = Math.abs(Number(row.quantity));
  const pnl = positionPnl(row, closed);
  const cost = entry * quantity;
  return Number.isFinite(cost) && cost > 0 ? (pnl / cost) * 100 : null;
}

function productName(row: any) {
  return row.product ?? row.product_type ?? row.order_type ?? "-";
}

function finiteOr(value: unknown, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function searchable(row: any) {
  return [row.symbol, row.side, row.status, row.product, row.product_type, row.order_type, row.broker_order_id]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

type PnlFilter = "all" | "profit" | "loss";

export default function PaperTrades() {
  const [positions, setPositions] = useState<any[]>([]);
  const [closedPositions, setClosedPositions] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>({});
  const [mode, setMode] = useState<TradingMode>(getCurrentMode());
  const [query, setQuery] = useState("");
  const [pnlFilter, setPnlFilter] = useState<PnlFilter>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [closingPosition, setClosingPosition] = useState<any>(null);
  const [closing, setClosing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [openPayload, closedPayload, summaryPayload] = await Promise.all([
        api.openPositions(), api.closedPositions(), api.positionSummary(),
      ]);
      setPositions(rowsFrom(openPayload));
      setClosedPositions(rowsFrom(closedPayload));
      setSummary(summaryPayload ?? {});
      setError(null);
    } catch (reason: any) {
      setError(reason?.response?.data?.detail ?? reason?.message ?? "Position data is unavailable.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const handleModeChange = () => {
      setMode(getCurrentMode());
      void load();
    };
    window.addEventListener("quantgrid-mode-change", handleModeChange);
    return () => window.removeEventListener("quantgrid-mode-change", handleModeChange);
  }, [load]);

  const filterRows = useCallback((rows: any[], closed: boolean) => {
    const normalizedQuery = query.trim().toLowerCase();
    return rows.filter((row) => {
      if (normalizedQuery && !searchable(row).includes(normalizedQuery)) return false;
      const pnl = positionPnl(row, closed);
      if (pnlFilter === "profit" && pnl <= 0) return false;
      if (pnlFilter === "loss" && pnl >= 0) return false;
      return true;
    });
  }, [pnlFilter, query]);

  const visibleOpen = useMemo(() => filterRows(positions, false), [filterRows, positions]);
  const visibleClosed = useMemo(() => filterRows(closedPositions, true), [closedPositions, filterRows]);
  const unrealizedPnl = finiteOr(summary.unrealized_pnl, positions.reduce((total, row) => total + positionPnl(row), 0));
  const realizedPnl = finiteOr(summary.realized_pnl, closedPositions.reduce((total, row) => total + positionPnl(row, true), 0));
  const totalPnl = finiteOr(summary.todays_pnl, unrealizedPnl + realizedPnl);
  const grossExposure = positions.reduce((total, row) => total + Math.abs(Number(row.quantity) || 0) * Math.abs(Number(row.current_price ?? row.entry_price ?? row.entry) || 0), 0);
  const closedWithPnl = closedPositions.filter((row) => Number.isFinite(positionPnl(row, true)));
  const winners = closedWithPnl.filter((row) => positionPnl(row, true) > 0).length;
  const winRate = closedWithPnl.length ? (winners / closedWithPnl.length) * 100 : 0;
  const averageClosedPnl = closedWithPnl.length ? realizedPnl / closedWithPnl.length : 0;
  const capital = finiteOr(summary.capital ?? summary.available_capital, 0);
  const utilisation = capital > 0 ? Math.min((grossExposure / capital) * 100, 100) : null;

  const closePosition = async () => {
    if (!closingPosition?.id) return;
    setClosing(true);
    setError(null);
    try {
      const exitPrice = Number(closingPosition.current_price);
      await api.exitPosition(closingPosition.id, {
        reason: "manual_exit",
        ...(Number.isFinite(exitPrice) && exitPrice > 0 ? { exit_price: exitPrice } : {}),
      });
      setMessage(`${closingPosition.symbol ?? "Position"} closed successfully.`);
      setClosingPosition(null);
      await load();
    } catch (reason: any) {
      setError(reason?.response?.data?.detail ?? reason?.message ?? "Position could not be closed.");
    } finally {
      setClosing(false);
    }
  };

  const renderRows = (rows: any[], closed: boolean) => rows.map((row) => {
    const pnl = positionPnl(row, closed);
    const change = positionChange(row, closed);
    const ltp = closed ? row.exit_price ?? row.current_price : row.current_price;
    return (
      <tr key={row.id ?? row.broker_order_id}>
        <td data-label="Side"><span className={`position-side ${String(row.side).toLowerCase()}`}>{row.side === "BUY" ? "B" : row.side === "SELL" ? "S" : row.side ?? "-"}</span></td>
        <td data-label="Instrument" className="position-instrument"><strong>{row.symbol ?? "-"}</strong><small>{row.broker_order_id ? `Order ${row.broker_order_id}` : closed && row.closed_at ? `Closed ${new Date(row.closed_at).toLocaleString()}` : row.opened_at ? `Opened ${new Date(row.opened_at).toLocaleString()}` : ""}</small></td>
        <td data-label="Product"><span className="position-product">{productName(row)}</span></td>
        <td data-label="Quantity">{number(row.quantity)}</td>
        <td data-label="Average price">{number(row.entry_price ?? row.entry)}</td>
        <td data-label={closed ? "Exit price" : "LTP"}>{number(ltp)}</td>
        <td data-label="P&L" className={pnl >= 0 ? "is-positive" : "is-negative"}><strong>{money(pnl)}</strong></td>
        <td data-label="Change" className={pnl >= 0 ? "is-positive" : "is-negative"}>{change === null ? "-" : `${change > 0 ? "+" : ""}${change.toFixed(2)}%`}</td>
        {!closed && <td data-label="Action"><button type="button" className="position-exit-button" onClick={() => setClosingPosition(row)} disabled={!row.id} aria-label={`Close ${row.symbol ?? "position"}`}>Close</button></td>}
      </tr>
    );
  });

  return (
    <section className="dashboard-page positions-page">
      <div className="page-heading dashboard-heading positions-heading">
        <div><span className="page-eyebrow">{mode} portfolio</span><h1>Positions</h1><p>Track open exposure and completed outcomes from the active {mode} account.</p></div>
        <button className="refresh-button" type="button" onClick={() => void load()} disabled={loading}>Refresh</button>
      </div>

      {loading && <Loader label={`Loading ${mode} positions...`} />}
      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {message && <div className="alert alert-success" role="status">{message}</div>}

      {!loading && !error && <>
        <section className="position-summary-bar" aria-label="Position summary">
          <div><span>Today&apos;s total P&amp;L</span><strong className={totalPnl >= 0 ? "is-positive" : "is-negative"}>{money(totalPnl)}</strong></div>
          <div><span>Open</span><strong>{summary.open_positions ?? positions.length}</strong></div>
          <div><span>Unrealized</span><strong className={unrealizedPnl >= 0 ? "is-positive" : "is-negative"}>{money(unrealizedPnl)}</strong></div>
          <div><span>Realized</span><strong className={realizedPnl >= 0 ? "is-positive" : "is-negative"}>{money(realizedPnl)}</strong></div>
          <div><span>Exposure</span><strong>{money(summary.current_exposure)}</strong></div>
          <span className={`position-mode-badge ${mode}`}>{mode === "paper" ? "Paper mode" : "Live mode"}</span>
        </section>

        <section className="portfolio-insight-grid" aria-label="Portfolio performance snapshot">
          <article className="portfolio-insight-card"><span>Gross exposure</span><strong>{money(grossExposure)}</strong><small>{positions.length} open instrument{positions.length === 1 ? "" : "s"} across the active account</small></article>
          <article className="portfolio-insight-card"><span>Capital utilisation</span><strong>{utilisation === null ? "—" : `${utilisation.toFixed(1)}%`}</strong><small>{capital > 0 ? `${money(capital)} allocated capital` : "Capital allocation is not available"}</small><i><b style={{ width: `${utilisation ?? 0}%` }} /></i></article>
          <article className="portfolio-insight-card"><span>Closed-trade win rate</span><strong>{closedWithPnl.length ? `${winRate.toFixed(1)}%` : "—"}</strong><small>{closedWithPnl.length ? `${winners} winners from ${closedWithPnl.length} completed trades` : "Awaiting completed trades"}</small></article>
          <article className="portfolio-insight-card"><span>Average realized P&amp;L</span><strong className={averageClosedPnl >= 0 ? "is-positive" : "is-negative"}>{closedWithPnl.length ? money(averageClosedPnl) : "—"}</strong><small>Per completed position today</small></article>
        </section>

        <nav className="portfolio-workflow-links" aria-label="Portfolio workflow"><a href="/trade">Open order terminal <span>↗</span></a><a href="/trade-journal">Review trade history <span>↗</span></a></nav>

        <div className="position-toolbar">
          <label className="position-search"><span className="sr-only">Search positions</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search instrument, side, product or order ID" /></label>
          <div className="position-filter" role="group" aria-label="Filter positions by profit and loss">
            {(["all", "profit", "loss"] as PnlFilter[]).map((value) => <button type="button" key={value} className={pnlFilter === value ? "active" : ""} onClick={() => setPnlFilter(value)}>{value === "all" ? "All" : value === "profit" ? "In profit" : "In loss"}</button>)}
          </div>
        </div>

        <section className="dashboard-section position-book">
          <div className="section-header"><div><span className="page-eyebrow">Active exposure</span><h2>Open positions</h2></div><span>{visibleOpen.length} of {positions.length}</span></div>
          <div className="table-wrap position-table-wrap"><table className="table position-table" aria-label="Open positions"><thead><tr><th>B/S</th><th>Instrument</th><th>Product</th><th>Qty</th><th>Avg price</th><th>LTP</th><th>P&amp;L</th><th>% Change</th><th>Action</th></tr></thead><tbody>
            {renderRows(visibleOpen, false)}
            {!visibleOpen.length && <tr className="position-empty-row"><td colSpan={9} className="empty-table-cell"><strong>{positions.length ? "No open positions match this filter" : `No open ${mode} positions`}</strong><span>{positions.length ? "Change the search or P&L filter." : `Positions opened in ${mode} mode will appear here.`}</span></td></tr>}
          </tbody></table></div>
        </section>

        <section className="dashboard-section position-book closed-position-book">
          <div className="section-header"><div><span className="page-eyebrow">Completed trades</span><h2>Closed positions</h2></div><span>{visibleClosed.length} of {closedPositions.length}</span></div>
          <div className="table-wrap position-table-wrap"><table className="table position-table" aria-label="Closed positions"><thead><tr><th>B/S</th><th>Instrument</th><th>Product</th><th>Qty</th><th>Avg price</th><th>Exit price</th><th>P&amp;L</th><th>% Change</th></tr></thead><tbody>
            {renderRows(visibleClosed, true)}
            {!visibleClosed.length && <tr className="position-empty-row"><td colSpan={8} className="empty-table-cell"><strong>{closedPositions.length ? "No closed positions match this filter" : `No closed ${mode} positions`}</strong><span>{closedPositions.length ? "Change the search or P&L filter." : "Completed positions will appear here with realized P&L."}</span></td></tr>}
          </tbody></table></div>
        </section>
      </>}

      {closingPosition && <div className="modal-backdrop" role="presentation"><div className="live-confirm-modal position-exit-modal" role="dialog" aria-modal="true" aria-labelledby="close-position-title">
        <div className="modal-header"><div><span className="page-eyebrow">Manual exit · {mode} mode</span><h2 id="close-position-title">Close {closingPosition.symbol} position?</h2><p>This exits the complete open quantity at the latest available price.</p></div><span className="environment-badge danger">CLOSE</span></div>
        <div className="confirm-grid"><span><strong>{closingPosition.side}</strong>Side</span><span><strong>{closingPosition.quantity}</strong>Quantity</span><span><strong>{closingPosition.entry_price ?? "-"}</strong>Entry</span><span><strong>{closingPosition.current_price ?? "Market"}</strong>Exit price</span><span><strong>{money(closingPosition.open_pnl)}</strong>Open P&amp;L</span></div>
        <div className="modal-actions"><button type="button" className="refresh-button" onClick={() => setClosingPosition(null)} disabled={closing}>Cancel</button><button type="button" className="primary-action close-position-action" onClick={() => void closePosition()} disabled={closing}>{closing ? "Closing…" : "Confirm close"}</button></div>
      </div></div>}
    </section>
  );
}
