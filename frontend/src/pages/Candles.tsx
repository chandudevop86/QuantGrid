import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import CandleChart, { type Candle } from "../components/CandleChart";

const intervals = [
  { label: "5m", value: "5m" },
  { label: "15m", value: "15m" },
  { label: "1hr", value: "60m" },
];

export default function Candles() {
  const [candles, setCandles] = useState<Candle[]>([]);
  const [source, setSource] = useState<string | null>(null);
  const [volumeStatus, setVolumeStatus] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [interval, setInterval] = useState(intervals[0].value);

  useEffect(() => {
    setLoading(true);
    setError(null);
    setWarning(null);

    api
      .candles("NIFTY", interval)
      .then((data) => {
        setCandles(Array.isArray(data?.candles) ? data.candles : []);
        setSource(data?.source ?? null);
        setVolumeStatus(data?.volume_status ?? null);
        setWarning(data?.warning ?? null);
      })
      .catch((err: any) => {
        const message = err?.message === "Network Error"
          ? "Cannot reach the market API. Check that the backend is running on port 8000."
          : err?.message ?? "Failed to load candles.";
        setError(message);
      })
      .finally(() => setLoading(false));
  }, [interval]);

  const latest = useMemo(() => candles[candles.length - 1], [candles]);
  const latestVolume =
    volumeStatus === "not_reported_for_index"
      ? "N/A"
      : latest?.volume?.toLocaleString() ?? "-";
  const volumeHelper =
    volumeStatus === "not_reported_for_index"
      ? "Index volume not reported"
      : source ?? "Market API";

  return (
    <section className="dashboard-page">
      <div className="page-heading">
        <h1>Candles</h1>
        <p>Market candle visualization for NIFTY live data.</p>
      </div>

      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {warning && !error && <div className="alert alert-warning" role="status">{warning}</div>}

      <div className="metric-grid">
        <div className="metric-card">
          <span className="metric-label">Symbol</span>
          <strong className="metric-value">NIFTY</strong>
          <span className="metric-helper">{candles.length} candles loaded</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Latest Close</span>
          <strong className="metric-value">{latest ? latest.close : "-"}</strong>
          <span className="metric-helper">{latest ? new Date(latest.timestamp).toLocaleString() : "Waiting for data"}</span>
        </div>
        <div className="metric-card">
          <span className="metric-label">Latest Volume</span>
          <strong className="metric-value">{latestVolume}</strong>
          <span className="metric-helper">{volumeHelper}</span>
        </div>
      </div>

      <div className="form-panel chart-panel">
        <div className="form-panel-header">
          <div>
            <h2>Price Action</h2>
            <p>{loading ? "Loading candles..." : "Open, high, low, and close across the selected timeline."}</p>
          </div>
          <div className="chart-controls">
            <div className="timeline-toggle" aria-label="Candle timeline">
              {intervals.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  onClick={() => setInterval(item.value)}
                  className={interval === item.value ? "active" : ""}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <span className={`status-pill${error ? " error" : ""}`}>
              {loading ? "Loading" : error ? "Offline" : source === "yahoo-finance" ? "Live" : "Fallback"}
            </span>
          </div>
        </div>

        <CandleChart candles={candles} />
      </div>
    </section>
  );
}
