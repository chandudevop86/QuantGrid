import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

type ScannerState = "all" | "active" | "rejected" | "stale";
type ScanRow = { id: string; state: Exclude<ScannerState, "all">; strategy: string; symbol: string; side: string; score: number | null; reason: string; updated?: string };

function asScore(value: unknown) { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : null; }
function time(value: unknown) { return value ? new Date(String(value)).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—"; }
function normalise(payload: any): ScanRow[] {
  const rows: ScanRow[] = [];
  const add = (items: any[], state: ScanRow["state"]) => items.forEach((item, index) => {
    const signal = item?.signal ?? item;
    const decision = item?.decision ?? item;
    rows.push({ id: `${state}-${signal?.id ?? signal?.strategy_name ?? "signal"}-${index}`, state, strategy: signal?.strategy_name ?? signal?.strategy ?? "Scanner", symbol: signal?.symbol ?? "NIFTY", side: signal?.side ?? "NEUTRAL", score: asScore(decision?.score ?? signal?.score ?? signal?.total_score), reason: decision?.reason ?? (state === "active" ? "Risk gate passed" : state === "stale" ? "Awaiting a fresh candle" : "Validation gate not passed"), updated: signal?.timestamp ?? signal?.created_at });
  });
  add(payload?.active_signals ?? [], "active"); add(payload?.rejected_signals ?? [], "rejected"); add(payload?.stale_signals ?? [], "stale");
  return rows.sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
}

export default function AiScanner() {
  const [payload, setPayload] = useState<any>(null), [loading, setLoading] = useState(true), [error, setError] = useState<string | null>(null), [filter, setFilter] = useState<ScannerState>("all"), [query, setQuery] = useState("");
  const load = useCallback(async () => { setLoading(true); try { setPayload(await api.latestSignals()); setError(null); } catch (reason: any) { setError(reason?.response?.data?.detail ?? reason?.message ?? "AI scanner data is unavailable."); } finally { setLoading(false); } }, []);
  useEffect(() => { void load(); const timer = window.setInterval(() => void load(), 30000); return () => window.clearInterval(timer); }, [load]);
  const rows = useMemo(() => normalise(payload), [payload]);
  const visible = useMemo(() => rows.filter((row) => (filter === "all" || row.state === filter) && `${row.strategy} ${row.symbol} ${row.side}`.toLowerCase().includes(query.toLowerCase())), [filter, query, rows]);
  const counts = useMemo(() => ({ active: rows.filter((row) => row.state === "active").length, rejected: rows.filter((row) => row.state === "rejected").length, stale: rows.filter((row) => row.state === "stale").length }), [rows]);
  return <section className="dashboard-page ai-scanner-page">
    <header className="page-heading dashboard-heading"><div><span className="page-eyebrow">QuantGrid intelligence</span><h1>AI Scanner</h1><p>Ranked opportunities and validation outcomes from the live signal pipeline.</p></div><div className="dashboard-actions"><span className="scanner-live">Streaming scan</span><button type="button" className="refresh-button" onClick={() => void load()} disabled={loading}>{loading ? "Scanning…" : "Refresh"}</button></div></header>
    {error && <div className="alert alert-error" role="alert">{error}</div>}
    <section className="scanner-summary" aria-label="Scanner summary"><article><span>Qualified</span><strong>{counts.active}</strong><small>Passed the current risk gate</small></article><article><span>Rejected</span><strong>{counts.rejected}</strong><small>Need confirmation or a stronger score</small></article><article><span>Stale</span><strong>{counts.stale}</strong><small>Waiting for a refreshed market candle</small></article><article><span>Coverage</span><strong>{rows.length}</strong><small>Signals evaluated in this scan</small></article></section>
    <section className="dashboard-section scanner-workbench"><div className="scanner-toolbar"><label><span className="sr-only">Search scanner results</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search symbol or strategy" /></label><div role="group" aria-label="Filter scanner results">{(["all", "active", "rejected", "stale"] as ScannerState[]).map((state) => <button type="button" className={filter === state ? "active" : ""} onClick={() => setFilter(state)} key={state}>{state === "all" ? "All" : state}</button>)}</div></div><div className="table-wrap"><table className="table scanner-table" aria-label="AI scanner results"><thead><tr><th>Status</th><th>Strategy</th><th>Instrument</th><th>Bias</th><th>AI score</th><th>Decision rationale</th><th>Updated</th><th /></tr></thead><tbody>{visible.map((row) => <tr key={row.id}><td><span className={`scanner-state ${row.state}`}>{row.state}</span></td><td>{row.strategy}</td><td><strong>{row.symbol}</strong></td><td className={row.side === "BUY" ? "is-positive" : row.side === "SELL" ? "is-negative" : ""}>{row.side}</td><td><span className="scanner-score">{row.score === null ? "—" : `${Math.round(row.score)}`}</span></td><td>{row.reason}</td><td>{time(row.updated)}</td><td>{row.state === "active" ? <Link to="/trade">Trade</Link> : <Link to="/copilot">Explain</Link>}</td></tr>)}{!loading && !visible.length && <tr><td colSpan={8}>No scanner results match this view. The scanner does not create trades automatically.</td></tr>}</tbody></table></div></section>
    <p className="scanner-disclaimer">AI scores prioritize and explain signals; they are not a recommendation or an execution instruction.</p>
  </section>;
}
