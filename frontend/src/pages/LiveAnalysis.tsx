import { useEffect, useState } from "react";
import { api } from "../api";
import { createSocket } from "../socket";

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

function isTerminalStatus(status: unknown) {
  return ["completed", "failed", "stale"].includes(String(status ?? "").toLowerCase());
}

export default function LiveAnalysis() {
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [wsWarning, setWsWarning] = useState<string | null>(null);
  const [strategy, setStrategy] = useState("breakout");
  const [autoTrade, setAutoTrade] = useState(true);

  const statusLabel = loading
    ? "Running"
    : error
      ? "Check"
      : result?.status
        ? String(result.status)
        : jobId
          ? "Submitted"
          : "Idle";

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
        auto_trade: autoTrade,
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

    let active = true;
    let socketAvailable = false;
    let ws: WebSocket | null = null;
    let pollId: number | null = null;
    let reconnectId: number | null = null;

    const refreshJob = async () => {
      try {
        const res = await api.getJobs();
        if (!active) return;

        const latestJob = Array.isArray(res?.jobs)
          ? res.jobs.find((job: any) => job.job_id === jobId)
          : null;

        if (latestJob) {
          setResult(latestJob);
        }
      } catch {
        if (active && !socketAvailable) {
          setWsWarning("Live websocket is unavailable, and the latest job status could not be fetched. The job was still submitted.");
        }
      }
    };

    const stopPolling = () => {
      if (pollId !== null) {
        window.clearInterval(pollId);
        pollId = null;
      }
    };

    const startPolling = () => {
      if (pollId !== null) return;
      void refreshJob();
      pollId = window.setInterval(() => {
        setResult((current: any) => {
          if (!isTerminalStatus(current?.status)) {
            void refreshJob();
          }

          return current;
        });
      }, 3000);
    };

    void refreshJob();

    const connect = () => {
      ws = createSocket();

      ws.onopen = () => {
        socketAvailable = true;
        setWsWarning(null);
        stopPolling();
        void refreshJob();
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.job_id === jobId) {
            setResult(data);
          }
        } catch {
          setWsWarning("Received an invalid live job update. Polling for the latest job status.");
          startPolling();
        }
      };

      ws.onerror = () => {
        ws?.close();
      };

      ws.onclose = () => {
        if (!active) return;
        socketAvailable = false;
        setWsWarning("Live websocket is unavailable. Polling for job updates every 3 seconds.");
        startPolling();
        reconnectId = window.setTimeout(connect, 3000);
      };
    };

    connect();

    return () => {
      active = false;
      stopPolling();
      if (reconnectId !== null) window.clearTimeout(reconnectId);
      ws?.close();
    };
  }, [jobId]);

  return (
    <section className="dashboard-page">
      <div className="page-heading">
        <h1>Live Analysis</h1>
        <p>Run a paper analysis job for the selected NIFTY strategy.</p>
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

          <label className="toggle-row">
            <input
              type="checkbox"
              checked={autoTrade}
              onChange={(event) => setAutoTrade(event.target.checked)}
            />
            <span>Auto paper trades</span>
          </label>

          <button
            type="button"
            onClick={run}
            disabled={loading}
            className="primary-action"
          >
            {loading ? "Running..." : `Run ${formatStrategyName(strategy)}`}
          </button>
        </div>

        <div className="form-panel signal-panel">
          <div className="form-panel-header">
            <div>
              <h2>Job Result</h2>
              <p>{jobId ? `Tracking job ${jobId}` : "No live-analysis job submitted yet."}</p>
            </div>
            <span className={`status-pill${error ? " error" : ""}`}>
              {formatStrategyName(statusLabel)}
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
