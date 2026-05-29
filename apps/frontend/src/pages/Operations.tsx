import { useEffect, useState } from "react";
import { api } from "../api";
import Loader from "../components/Loader";

export default function Operations() {
  const [operations, setOperations] = useState<any>(null);
  const [auditEvents, setAuditEvents] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    const load = () => {
      Promise.all([
        api.operationsStatus(),
        api.auditTrail().catch(() => ({ events: [] })),
      ])
        .then(([data, auditData]) => {
          if (!isMounted) return;
          setOperations(data);
          setAuditEvents(Array.isArray(auditData?.events) ? auditData.events : []);
        })
        .catch(() => {
          if (isMounted) setError("Operations API is not available.");
        });
    };
    load();
    const id = window.setInterval(load, 30000);
    return () => {
      isMounted = false;
      window.clearInterval(id);
    };
  }, []);

  const observability = operations?.observability;
  const health = operations?.system_health;

  return (
    <section className="dashboard-page">
      <div className="page-heading">
        <h1>Operations</h1>
        <p>Production health, feed freshness, and trading telemetry.</p>
      </div>

      {!operations && !error && <Loader label="Loading operations..." />}
      {error && <p className="error-text">{error}</p>}

      {operations && (
        <>
        <div className="metric-grid observability-grid">
          <div className="metric-card">
            <span className="metric-label">WebSocket Connections</span>
            <strong className="metric-value">{observability?.websocket_connections ?? 0}</strong>
            <span className="metric-helper">Active realtime clients</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">API Latency</span>
            <strong className="metric-value">{observability?.api_latency_status ?? "tracked"}</strong>
            <span className="metric-helper">Prometheus histogram: api_request_latency_seconds</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Signal Generation</span>
            <strong className="metric-value">{observability?.signal_generation_metrics}</strong>
            <span className="metric-helper">Prometheus counter</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Rejected Orders</span>
            <strong className="metric-value">{observability?.rejected_order_metrics}</strong>
            <span className="metric-helper">Safety gate counter</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Feed Delay</span>
            <strong className="metric-value">{observability?.feed_delay_seconds ?? "-"}s</strong>
            <span className="metric-helper">Latest NIFTY 1m candle</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Redis</span>
            <strong className="metric-value">{health?.redis?.connected ? "Healthy" : "Disconnected"}</strong>
            <span className="metric-helper">{health?.redis?.message}</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Database</span>
            <strong className="metric-value">{health?.db?.healthy ? "Healthy" : "Degraded"}</strong>
            <span className="metric-helper">{health?.db?.message}</span>
          </div>
        </div>

        <div className="dashboard-section">
          <div className="section-header">
            <h2>Audit Trail</h2>
            <span>Latest {auditEvents.length} trading events</span>
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>User</th>
                  <th>Action</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {auditEvents.map((event) => (
                  <tr key={event.id}>
                    <td>{event.timestamp ? new Date(event.timestamp).toLocaleString() : "-"}</td>
                    <td>{event.user ?? "system"}</td>
                    <td>{event.action ?? "-"}</td>
                    <td>{event.status ?? "-"}</td>
                  </tr>
                ))}
                {auditEvents.length === 0 && (
                  <tr>
                    <td colSpan={4}>No audit events recorded yet.</td>
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
