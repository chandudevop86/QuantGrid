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
  status: "active" | "rejected" | "stale";
  detail: string;
  timestamp?: string;
};

function signalRows(payload: any): SignalRow[] {
  const active = (payload?.active_signals ?? []).map((signal: any, index: number) => ({
    id: `active-${signal.id ?? signal.timestamp ?? index}`,
    strategy: signal.strategy_name ?? signal.strategy ?? "Strategy",
    side: signal.side ?? signal.signal ?? "Waiting",
    status: "active" as const,
    detail: signal.reason ?? "Passed signal validation",
    timestamp: signal.timestamp ?? signal.signal_time,
  }));
  const rejected = (payload?.rejected_signals ?? []).map((item: any, index: number) => ({
    id: `rejected-${item.id ?? item.signal?.timestamp ?? index}`,
    strategy: item.signal?.strategy_name ?? item.strategy_name ?? "Strategy",
    side: item.signal?.side ?? item.side ?? "No trade",
    status: "rejected" as const,
    detail: item.decision?.reason ?? item.reason ?? "Did not pass validation",
    timestamp: item.signal?.timestamp ?? item.timestamp,
  }));
  const stale = (payload?.stale_signals ?? []).map((item: any, index: number) => ({
    id: `stale-${item.id ?? item.signal?.timestamp ?? index}`,
    strategy: item.signal?.strategy_name ?? item.strategy_name ?? "Strategy",
    side: item.signal?.side ?? item.side ?? "Expired",
    status: "stale" as const,
    detail: item.decision?.reason ?? "Signal is no longer current",
    timestamp: item.signal?.timestamp ?? item.timestamp,
  }));
  return [...active, ...rejected, ...stale].slice(0, 5);
}

export default function RecentSignals() {
  const [rows, setRows] = useState<SignalRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setRows(signalRows(await api.latestSignals())); }
    catch (caught: any) { setError(caught?.message ?? "Recent signals could not be loaded."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);

  return <article className="qg-card qg-recent-signals" aria-labelledby="recent-signals-title">
    <div className="qg-section-heading"><div><span>Latest validated activity</span><h2 id="recent-signals-title">Recent signals</h2></div><Link to="/signals">View all</Link></div>
    {loading && <div className="qg-signals-loading" role="status">Loading recent signals…</div>}
    {!loading && error && <ErrorState message={error} onRetry={() => void load()} />}
    {!loading && !error && rows.length === 0 && <EmptyState title="No recent signals" message="Qualified, rejected, and stale signals will appear here when available." />}
    {!loading && !error && rows.length > 0 && <ul className="qg-signal-list">{rows.map((row) => <li key={row.id}><div><strong>{row.strategy}</strong><span>{row.detail}</span></div><div><StatusBadge tone={row.status === "active" ? "positive" : row.status === "rejected" ? "danger" : "warning"}>{row.status}</StatusBadge><strong>{row.side}</strong>{row.timestamp && <time dateTime={row.timestamp}>{new Date(row.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time>}</div></li>)}</ul>}
  </article>;
}
