import { useEffect, useState } from "react";
import { api } from "../api";

const strategies = [
  "amd",
  "breakout",
  "btst",
  "mean_reversion",
  "mtf",
  "supply_demand",
];

function formatStrategyName(strategy: string) {
  return strategy
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export default function LiveAnalysis() {
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [wsWarning, setWsWarning] = useState<string | null>(null);
  const [strategy, setStrategy] = useState("breakout");

  const run = async () => {
    try {
      setLoading(true);
      setError(null);
      setWsWarning(null);

      const res = await api.runAnalysis({
        symbol: "NIFTY",
        interval: "1m",
        period: "1d",
        strategy,
        capital: 100000,
        risk_pct: 1,
        rr_ratio: 2,
      });

      setJobId(res.job_id);
      setResult(res);
    } catch (err: any) {
      const message =
        err?.response?.data?.detail ??
        err?.message ??
        "Failed to run analysis";
      setError(
        message === "Network Error"
          ? "Cannot reach the dashboard API. Check that the backend is running on port 8000."
          : message
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!jobId) return;

    const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
    const wsHost = window.location.hostname;
    const wsUrl = import.meta.env.VITE_WS_URL ?? `${wsProtocol}://${wsHost}:8005/ws`;
    const ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.job_id === jobId) {
        setResult(data);
      }
    };

    ws.onerror = () => {
      setWsWarning("Live websocket is unavailable, so this page will not receive push updates. The job was still submitted.");
    };

    return () => ws.close();
  }, [jobId]);

  return (
    <section className="dashboard-page">
      <div className="page-heading">
        <h1>Live Analysis</h1>
        <p>Create a queued analysis job for the selected NIFTY strategy.</p>
      </div>

      <div className="strategy-layout">
        <div className="form-panel">
          <div className="form-panel-header">
            <div>
              <h2>Strategy</h2>
              <p>Choose the strategy before creating the job.</p>
            </div>
          </div>

          <div className="strategy-grid">
            {strategies.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setStrategy(item)}
                className={`strategy-chip${strategy === item ? " active" : ""}`}
              >
                {formatStrategyName(item)}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={run}
            disabled={loading}
            className="primary-action"
          >
            {loading ? "Queueing..." : `Run ${formatStrategyName(strategy)}`}
          </button>
        </div>

        <div className="form-panel signal-panel">
          <div className="form-panel-header">
            <div>
              <h2>Job Result</h2>
              <p>{jobId ? `Tracking job ${jobId}` : "No live-analysis job submitted yet."}</p>
            </div>
            <span className={`status-pill${error ? " error" : ""}`}>
              {loading ? "Queueing" : error ? "Check" : jobId ? "Queued" : "Idle"}
            </span>
          </div>

          {error && (
            <div className="alert alert-error" role="alert">
              {error}
            </div>
          )}

          {wsWarning && !error && (
            <div className="alert alert-warning" role="status">
              {wsWarning}
            </div>
          )}

          <pre>
            {result
              ? JSON.stringify(result, null, 2)
              : "Select a strategy and run analysis to create a job."}
          </pre>
        </div>
      </div>
    </section>
  );
}
