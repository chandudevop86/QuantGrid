import { useMemo } from "react";
import { useStrategySignals } from "../hooks/useAutoSignals";

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

export default function Strategies() {
  const strategyList = useMemo(() => strategies, []);
  const { signalsByStrategy, loading } = useStrategySignals(strategyList, 5000);

  return (
    <section className="dashboard-page">
      <div className="page-heading">
        <h1>Strategies</h1>
        <p>Watch strategy-wise NIFTY signals refresh every 5 seconds.</p>
      </div>

      <div className="strategy-signal-grid">
        {strategyList.map((strategy) => {
          const signal = signalsByStrategy[strategy];
          const hasSignalError = Boolean(signal?.error);
          const signals = Array.isArray(signal?.data) ? signal.data : [];
          const hasSignals = signals.length > 0;
          const updatedAt = signal?.updated_at
            ? new Date(signal.updated_at).toLocaleTimeString()
            : null;

          return (
            <div key={strategy} className="form-panel signal-panel strategy-signal-card">
              <div className="form-panel-header">
                <div>
                  <h2>{formatStrategyName(strategy)}</h2>
                  <p>{updatedAt ? `Updated ${updatedAt}` : "Waiting for first refresh."}</p>
                </div>
                <span className={`status-pill${hasSignalError ? " error" : ""}`}>
                  {loading && !signal ? "Updating" : hasSignalError ? "Offline" : "Live"}
                </span>
              </div>

              {hasSignalError && (
                <div className="alert alert-error" role="alert">
                  Signal API unavailable. Check that the trading backend is running on port 8000.
                </div>
              )}

              {!hasSignalError && signal && (
                <div className="signal-summary">
                  <span>
                    <strong>{signal.candles_analyzed ?? 0}</strong>
                    Candles
                  </span>
                  <span>
                    <strong>{signals.length}</strong>
                    Signals
                  </span>
                  <span>
                    <strong>{signal.market_data?.source ?? "-"}</strong>
                    Source
                  </span>
                </div>
              )}

              {!hasSignalError && signal && !hasSignals && (
                <div className="alert alert-warning" role="status">
                  No validated signal right now.
                </div>
              )}

              <pre>
                {signal
                  ? JSON.stringify(hasSignalError ? signal : signals, null, 2)
                  : "Waiting for the first signal response..."}
              </pre>
            </div>
          );
        })}
      </div>
    </section>
  );
}
