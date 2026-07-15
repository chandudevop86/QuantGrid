import { useEffect, useState } from "react";
import { api } from "../api";
import Loader from "../components/Loader";
import { useOperationsStatus } from "../context/OperationsStatusContext";

export default function Operations() {
  const { operations, loading, error: operationsError } = useOperationsStatus();
  const [auditEvents, setAuditEvents] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    const load = () => {
      api.auditTrail()
        .then((auditData) => {
          if (!isMounted) return;
          setAuditEvents(Array.isArray(auditData?.events) ? auditData.events : []);
          setError(null);
        })
        .catch((err) => {
          if (!isMounted) return;
          const status = err?.response?.status;
          if (status === 403) {
            setError("Audit trail requires admin or ops role.");
          } else if (status === 401) {
            setError("Session expired. Sign in again.");
          } else {
            setError("Audit trail is unavailable.");
          }
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
  const metricValue = (...values: any[]) => {
    const value = values.find((item) => item !== undefined && item !== null && item !== "");
    if (value && typeof value === "object") {
      if ("validated" in value) return value.validated;
      if ("generated" in value) return value.generated;
      if ("count" in value) return value.count;
      if ("total" in value) return value.total;
      return "-";
    }
    return value ?? 0;
  };
  const formatMs = (value: any) => {
    const numeric = Number(value ?? 0);
    return Number.isFinite(numeric) ? `${numeric}ms` : "-";
  };
  const formatMetadata = (metadata: any) => {
    if (!metadata || Object.keys(metadata).length === 0) return "-";
    return JSON.stringify(metadata);
  };

  return (
    <section className="dashboard-page">
      <div className="page-heading">
        <h1>Operations</h1>
        <p>Production health, feed freshness, and trading telemetry.</p>
      </div>

      {loading && !operations && <Loader label="Loading operations..." />}
      {(error || operationsError) && <p className="error-text">{error || operationsError}</p>}

      {operations && (
        <>
        <div className="metric-grid observability-grid">
          <div className="metric-card">
            <span className="metric-label">WebSocket Connections</span>
            <strong className="metric-value">{metricValue(observability?.websocket_connection_count, observability?.websocket_connections)}</strong>
            <span className="metric-helper">Active realtime clients</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">API Latency</span>
            <strong className="metric-value">{formatMs(metricValue(observability?.api_latency_ms, observability?.api_latency_status))}</strong>
            <span className="metric-helper">Latest request latency</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Signal Generation</span>
            <strong className="metric-value">{metricValue(observability?.signal_generation_metrics?.generated, observability?.signal_generation_metrics)}</strong>
            <span className="metric-helper">Generated signals</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Strategy Executions</span>
            <strong className="metric-value">{metricValue(observability?.strategy_execution_count, observability?.strategy_execution_metrics)}</strong>
            <span className="metric-helper">Strategy runs</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Signal Count</span>
            <strong className="metric-value">{metricValue(observability?.signal_generation_metrics?.validated, observability?.signal_count_metrics)}</strong>
            <span className="metric-helper">Validated signals</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Failed Executions</span>
            <strong className="metric-value">{metricValue(observability?.failed_strategy_execution_count, observability?.failed_strategy_execution_metrics)}</strong>
            <span className="metric-helper">Strategy error counter</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Option Chain Failures</span>
            <strong className="metric-value">{metricValue(observability?.option_chain_failure_count, observability?.option_chain_failure_metrics)}</strong>
            <span className="metric-helper">Provider fallback counter</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Rejected Orders</span>
            <strong className="metric-value">{metricValue(observability?.rejected_order_count, observability?.rejected_order_metrics)}</strong>
            <span className="metric-helper">Safety gate counter</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Feed Delay</span>
            <strong className="metric-value">{metricValue(observability?.feed_delay_metrics?.seconds, observability?.feed_delay_seconds)}s</strong>
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
          <div className="metric-card">
            <span className="metric-label">Market Data</span>
            <strong className="metric-value">{health?.market_data?.healthy ? "Healthy" : "Warming"}</strong>
            <span className="metric-helper">{health?.market_data?.candles ?? 0} stored candles</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Strategy Engine</span>
            <strong className="metric-value">{health?.strategy_engine?.healthy ? "Healthy" : "Review"}</strong>
            <span className="metric-helper">{health?.strategy_engine?.registered?.length ?? 0} registered strategies</span>
          </div>
        </div>

        <div className="dashboard-section">
          <div className="section-header">
            <h2>Audit Trail</h2>
            <span>Latest {auditEvents.length} audit events</span>
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>User</th>
                  <th>Role</th>
                  <th>Action</th>
                  <th>Status</th>
                  <th>Request ID</th>
                  <th>Reason</th>
                  <th>Metadata</th>
                </tr>
              </thead>
              <tbody>
                {auditEvents.map((event) => (
                  <tr key={event.id}>
                    <td>{event.timestamp ? new Date(event.timestamp).toLocaleString() : "-"}</td>
                    <td>{event.user ?? "system"}</td>
                    <td>{event.role ?? "-"}</td>
                    <td>{event.action ?? "-"}</td>
                    <td>{event.status ?? "-"}</td>
                    <td>{event.request_id ?? "-"}</td>
                    <td>{event.reason ?? "-"}</td>
                    <td>{formatMetadata(event.metadata)}</td>
                  </tr>
                ))}
                {auditEvents.length === 0 && (
                  <tr>
                    <td colSpan={8}>No audit events recorded yet.</td>
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
