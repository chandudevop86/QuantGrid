import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import CandleChart, { type Candle } from "../components/CandleChart";

const intervals = [
  { label: "1m", value: "1m" },
  { label: "5m", value: "5m" },
  { label: "15m", value: "15m" },
  { label: "1hr", value: "60m" },
  { label: "4hr", value: "4h" },
  { label: "1day", value: "1d" },
];

const refreshMs = 15000;
const minVisibleCandles = 10;
const maxVisibleCandles = 100;

export default function Candles() {
  const [candles, setCandles] = useState<Candle[]>([]);
  const [source, setSource] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedInterval, setSelectedInterval] = useState(intervals[0].value);
  const [visibleCount, setVisibleCount] = useState(40);

  const loadCandles = useCallback((showInitialLoading = false) => {
    if (showInitialLoading) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    setError(null);
    setWarning(null);

    return api
      .candles("NIFTY", selectedInterval)
      .then((data) => {
        setCandles(Array.isArray(data?.candles) ? data.candles : []);
        setSource(data?.source ?? null);
        setWarning(data?.warning ?? null);
        setLastRefreshed(new Date());
      })
      .catch((err: any) => {
        const message = err?.message === "Network Error"
          ? "Cannot reach the market API. Check that the backend is running on port 8000."
          : err?.message ?? "Failed to load candles.";
        setError(message);
      })
      .finally(() => {
        setLoading(false);
        setRefreshing(false);
      });
  }, [selectedInterval]);

  useEffect(() => {
    void loadCandles(true);

    const refreshTimer = window.setInterval(() => {
      void loadCandles(false);
    }, refreshMs);

    return () => window.clearInterval(refreshTimer);
  }, [loadCandles]);

  const refreshLabel = lastRefreshed
    ? `Updated ${lastRefreshed.toLocaleTimeString()}`
    : "Auto refresh every 15s";
  const zoomMaximum = Math.max(minVisibleCandles, Math.min(maxVisibleCandles, candles.length || maxVisibleCandles));
  const clampedVisibleCount = Math.min(visibleCount, zoomMaximum);
  const visibleCandles = candles.slice(-clampedVisibleCount);
  const changeZoom = (next: number) => {
    setVisibleCount(Math.max(minVisibleCandles, Math.min(zoomMaximum, next)));
  };

  return (
    <section className="dashboard-page candles-page">
      <div className="page-heading">
        <h1>Candles</h1>
        <p>NIFTY price action across selectable market intervals.</p>
      </div>

      {error && <div className="alert alert-error" role="alert">{error}</div>}
      {warning && !error && <div className="alert alert-warning" role="status">{warning}</div>}

      <div className="form-panel chart-panel">
        <div className="form-panel-header">
          <div>
            <h2>NIFTY Candles</h2>
            <p>{loading ? "Loading candles..." : `${candles.length} candles · ${refreshLabel}`}</p>
          </div>
          <div className="chart-controls">
            <div className="candle-zoom" role="group" aria-label="Candle zoom controls">
              <button type="button" onClick={() => changeZoom(clampedVisibleCount + 10)} disabled={clampedVisibleCount >= zoomMaximum} aria-label="Zoom out to show more candles">−</button>
              <label htmlFor="candle-zoom-range">Zoom <strong>{clampedVisibleCount}</strong></label>
              <input
                id="candle-zoom-range"
                type="range"
                min={minVisibleCandles}
                max={zoomMaximum}
                step="10"
                value={clampedVisibleCount}
                onChange={(event) => changeZoom(Number(event.target.value))}
                aria-valuetext={`${clampedVisibleCount} candles visible`}
              />
              <button type="button" onClick={() => changeZoom(clampedVisibleCount - 10)} disabled={clampedVisibleCount <= minVisibleCandles} aria-label="Zoom in to show fewer candles">+</button>
            </div>
            <div className="timeline-toggle" aria-label="Candle timeline">
              {intervals.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  onClick={() => setSelectedInterval(item.value)}
                  className={selectedInterval === item.value ? "active" : ""}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <button
              type="button"
              className="refresh-button"
              onClick={() => void loadCandles(false)}
              disabled={loading || refreshing}
            >
              Refresh
            </button>
            <span className={`status-pill${error ? " error" : ""}`}>
              {loading ? "Loading" : refreshing ? "Refreshing" : error ? "Offline" : source === "yahoo-finance" ? "Live" : "Fallback"}
            </span>
          </div>
        </div>

        <CandleChart candles={visibleCandles} />
      </div>
    </section>
  );
}
