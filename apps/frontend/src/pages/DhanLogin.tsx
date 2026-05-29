import { useEffect, useState } from "react";
import { api } from "../api";
import { useUiMode } from "../hooks/useUiMode";

export default function DhanLogin() {
  const [clientId, setClientId] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [persist, setPersist] = useState(true);
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const developerMode = useUiMode() === "developer";

  const loadStatus = async () => {
    try {
      const data = await api.brokerStatus();
      setStatus(data);
    } catch {
      setStatus(null);
    }
  };

  useEffect(() => {
    void loadStatus();
  }, []);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const result = await api.dhanLogin({
        client_id: clientId.trim(),
        access_token: accessToken.trim(),
        persist,
      });
      setStatus(result);
      setAccessToken("");
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? err?.message ?? "Dhan login failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="dashboard-page">
      <div className="page-heading">
        <h1>Dhan Login</h1>
        <p>Connect Dhan credentials for broker status checks. Execution remains paper-only.</p>
      </div>

      <div className="metric-grid">
        <div className="metric-card">
          <span className="metric-label">Provider</span>
          <strong className="metric-value">{status?.provider ?? "dhan"}</strong>
          <span className="metric-helper">{status?.configured ? "Configured" : "Not configured"}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Connection</span>
          <strong className="metric-value">{status?.connected ? "Connected" : "Offline"}</strong>
          <span className="metric-helper">{status?.client_id ? `Client ${status.client_id}` : "Awaiting login"}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Trading Mode</span>
          <strong className="metric-value">Paper</strong>
          <span className="metric-helper">Real-money broker orders disabled</span>
        </div>
      </div>

      <form className="form-panel" onSubmit={submit}>
        <div className="form-panel-header">
          <div>
            <h2>Dhan Credentials</h2>
            <p>{status?.message ?? "Enter your Dhan client ID and access token."}</p>
          </div>
          <span className={`status-pill${status?.connected ? "" : " stale"}`}>
            {status?.connected ? "Connected" : "Check"}
          </span>
        </div>

        <div className="field-grid">
          <label>
            <span>Client ID</span>
            <input
              value={clientId}
              onChange={(event) => setClientId(event.target.value)}
              placeholder="Dhan client ID"
              required
            />
          </label>
          <label>
            <span>Access Token</span>
            <input
              value={accessToken}
              onChange={(event) => setAccessToken(event.target.value)}
              placeholder="Dhan access token"
              type="password"
              required
            />
          </label>
        </div>

        <label className="toggle-row">
          <input
            type="checkbox"
            checked={persist}
            onChange={(event) => setPersist(event.target.checked)}
          />
          <span>Save to backend .env</span>
        </label>

        <button type="submit" className="primary-action" disabled={loading}>
          {loading ? "Checking..." : "Login to Dhan"}
        </button>

        {error && <div className="alert alert-error">{error}</div>}
        {status?.message && !error && <div className="alert alert-success">{status.message}</div>}

        {developerMode && (
          <details className="technical-details" open>
            <summary>Broker Status Payload</summary>
            <pre>{JSON.stringify(status, null, 2)}</pre>
          </details>
        )}
      </form>
    </section>
  );
}
