import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

function label(value: unknown, fallback = "Unavailable") { return value === null || value === undefined || value === "" ? fallback : String(value); }

export default function ManagementHub() {
  const [broker, setBroker] = useState<any>(null), [circuit, setCircuit] = useState<any>(null), [loading, setLoading] = useState(true), [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => { setLoading(true); try { const [brokerStatus, circuitStatus] = await Promise.all([api.brokerStatus(), api.brokerCircuitBreakerStatus().catch(() => null)]); setBroker(brokerStatus); setCircuit(circuitStatus); setError(null); } catch (reason: any) { setError(reason?.response?.data?.detail ?? reason?.message ?? "Broker management status is unavailable."); } finally { setLoading(false); } }, []);
  useEffect(() => { void load(); }, [load]);
  const connected = Boolean(broker?.connected), breakerOpen = Boolean(circuit?.open ?? circuit?.is_open ?? circuit?.tripped);
  return <section className="dashboard-page management-hub-page">
    <header className="page-heading dashboard-heading"><div><span className="page-eyebrow">Administration</span><h1>Operations & Broker Management</h1><p>Operational status and access controls for the active QuantGrid environment.</p></div><button type="button" className="refresh-button" disabled={loading} onClick={() => void load()}>{loading ? "Checking…" : "Refresh"}</button></header>
    {error && <div className="alert alert-error" role="alert">{error}</div>}
    <section className="management-command-strip" aria-label="Broker operation status"><article><span>Broker</span><strong className={connected ? "is-positive" : "is-negative"}>{connected ? "Connected" : "Disconnected"}</strong><small>{label(broker?.provider, "No configured provider")}</small></article><article><span>Execution guard</span><strong>{broker?.paper_only === false ? "Review required" : "Paper only"}</strong><small>{broker?.paper_only === false ? "Live execution requires explicit controls" : "Real-money broker orders are disabled"}</small></article><article><span>Circuit breaker</span><strong className={breakerOpen ? "is-negative" : "is-positive"}>{breakerOpen ? "Open" : "Protected"}</strong><small>{label(circuit?.message, breakerOpen ? "Execution has been paused" : "No active trading halt")}</small></article></section>
    <section className="management-link-grid" aria-label="Management workspaces"><Link to="/dhan-login"><span>Broker Connection</span><strong>Dhan credential setup</strong><small>Store and validate broker credentials through the protected setup flow.</small><i>↗</i></Link><Link to="/security"><span>Security Posture</span><strong>Controls and findings</strong><small>Review application, infrastructure, and identity risks.</small><i>↗</i></Link><Link to="/admin/users"><span>User Administration</span><strong>Users and roles</strong><small>Create accounts, rotate passwords, and manage role access.</small><i>↗</i></Link><Link to="/operations"><span>System Operations</span><strong>Service health</strong><small>Inspect API, database, jobs, and application health.</small><i>↗</i></Link></section>
    <section className="management-policy"><div><span className="page-eyebrow">Credential policy</span><h2>Secrets remain server-managed</h2><p>API tokens and broker credentials are never displayed in this workspace. Use broker setup to submit credentials over the authenticated backend flow, then verify only connection status here.</p></div><Link to="/dhan-login">Manage broker credentials <span>↗</span></Link></section>
  </section>;
}
