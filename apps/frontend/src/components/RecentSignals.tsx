import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import EmptyState from "./EmptyState";
import ErrorState from "./ErrorState";
import StatusBadge from "./StatusBadge";

type SignalRow = {
  id: string;
  strategy: string;
  side: string;
  confidence?: number;
  status: "active" | "rejected" | "stale";
  detail: string;
  timestamp?: string;
};

function signalRows(payload: any): SignalRow[] {
  const active = (payload?.active_signals ?? []).map((signal: any, index: number) => ({
    id: `active-${signal.id ?? signal.timestamp ?? index}`,
    strategy: signal.strategy_name ?? signal.strategy ?? "Strategy",
    side: signal.side ?? signal.signal ?? "Waiting",
    confidence: Number(signal.confidence ?? signal.score ?? signal.signal_score),
    status: "active" as const,
    detail: signal.reason ?? "Passed signal validation",
    timestamp: signal.timestamp ?? signal.signal_time,
  }));
  const rejected = (payload?.rejected_signals ?? []).map((item: any, index: number) => ({
    id: `rejected-${item.id ?? item.signal?.timestamp ?? index}`,
    strategy: item.signal?.strategy_name ?? item.strategy_name ?? "Strategy",
    side: item.signal?.side ?? item.side ?? "No trade",
    confidence: Number(item.signal?.confidence ?? item.signal?.score ?? item.decision?.confidence),
    status: "rejected" as const,
    detail: item.decision?.reason ?? item.reason ?? "Did not pass validation",
    timestamp: item.signal?.timestamp ?? item.timestamp,
  }));
  const stale = (payload?.stale_signals ?? []).map((item: any, index: number) => ({
    id: `stale-${item.id ?? item.signal?.timestamp ?? index}`,
    strategy: item.signal?.strategy_name ?? item.strategy_name ?? "Strategy",
    side: item.signal?.side ?? item.side ?? "Expired",
    confidence: Number(item.signal?.confidence ?? item.signal?.score ?? item.decision?.confidence),
    status: "stale" as const,
    detail: item.decision?.reason ?? "Signal is no longer current",
    timestamp: item.signal?.timestamp ?? item.timestamp,
  }));
  return [...active, ...rejected, ...stale]
    .sort((a, b) => Date.parse(b.timestamp ?? "") - Date.parse(a.timestamp ?? ""))
    ;
}

export default function RecentSignals({ limit = 5 }: { limit?: number }) {
  const [rows, setRows] = useState<SignalRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setRows(signalRows(await api.latestSignals()).slice(0, Math.max(1, limit))); }
    catch (caught: any) { setError(caught?.message ?? "Recent signals could not be loaded."); }
    finally { setLoading(false); }
  }, [limit]);
  useEffect(() => { void load(); }, [load]);

  return <article className="qg-card qg-recent-signals" aria-labelledby="recent-signals-title">
    <div className="qg-section-heading"><div><span>Latest validated activity</span><h2 id="recent-signals-title">Recent signals</h2></div><Link to="/signals">View all</Link></div>
    {loading && <div className="qg-signals-loading" role="status">Loading recent signals…</div>}
    {!loading && error && <ErrorState message={error} onRetry={() => void load()} />}
    {!loading && !error && rows.length === 0 && <EmptyState title="No recent signals" message="Qualified, rejected, and stale signals will appear here when available." />}
    {!loading && !error && rows.length > 0 && <div className="qg-signal-table" role="table" aria-label="Five most recent signals">
      <div className="qg-signal-header" role="row"><span role="columnheader">Time</span><span role="columnheader">Decision</span><span role="columnheader">Confidence</span><span role="columnheader">Status</span></div>
      <ul className="qg-signal-list">{rows.map((row) => <li key={row.id} role="row" title={row.detail}>
        <time role="cell" data-label="Time" dateTime={row.timestamp}>{row.timestamp ? new Date(row.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—"}</time>
        <strong role="cell" data-label="Decision">{row.side}</strong>
        <span role="cell" data-label="Confidence">{Number.isFinite(row.confidence) ? `${Math.round(Number(row.confidence))}%` : "—"}</span>
        <span role="cell" data-label="Status"><StatusBadge tone={row.status === "active" ? "positive" : row.status === "rejected" ? "danger" : "warning"}>{row.status}</StatusBadge></span>
      </li>)}</ul>
    </div>}
  </article>;
}
