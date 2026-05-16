import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import CandleChart, { type Candle } from "../components/CandleChart";

export default function Candles() {
  const [candles, setCandles] = useState<Candle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .candles("NIFTY")
      .then((data) => setCandles(Array.isArray(data?.candles) ? data.candles : []))
      .catch((err: any) => {
        const message = err?.message === "Network Error"
          ? "Cannot reach the market API. Check that the backend is running on port 8000."
          : err?.message ?? "Failed to load candles.";
        setError(message);
      })
      .finally(() => setLoading(false));
  }, []);

  const latest = useMemo(() => candles[candles.length - 1], [candles]);

  return (
    <section className="dashboard-page">
      <div className="page-heading">
        <h1>Candles</h1>
        <p>Market candle visualization for the NIFTY sample feed.</p>
      </div>

      {error && <div className="alert alert-error" role="alert">{error}</div>}

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
          <strong className="metric-value">{latest?.volume ?? "-"}</strong>
          <span className="metric-helper">Market API sample</span>
        </div>
      </div>

      <div className="form-panel chart-panel">
        <div className="form-panel-header">
          <div>
            <h2>Price Action</h2>
            <p>{loading ? "Loading candles..." : "Open, high, low, and close over recent minutes."}</p>
          </div>
          <span className={`status-pill${error ? " error" : ""}`}>
            {loading ? "Loading" : error ? "Offline" : "Live"}
          </span>
        </div>

        <CandleChart candles={candles} />
      </div>
    </section>
  );
}
