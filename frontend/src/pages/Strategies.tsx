import { useState } from "react";
import { useAutoSignals } from "../hooks/useAutoSignals";

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
  const [selectedStrategy, setSelectedStrategy] = useState<string | null>(strategies[0]);

  const { signal, loading } = useAutoSignals(selectedStrategy, 5000);
  const hasSignalError = Boolean(signal?.error);

  return (
    <section className="dashboard-page">
      <div className="page-heading">
        <h1>Strategies</h1>
        <p>Run sample NIFTY signal checks and watch the active strategy response.</p>
      </div>

      <div className="strategy-layout">
        <div className="form-panel">
          <div className="form-panel-header">
            <div>
              <h2>Strategy Set</h2>
              <p>Select one strategy to poll every 5 seconds.</p>
            </div>
          </div>

          <div className="strategy-grid">
            {strategies.map((strategy) => (
              <button
                key={strategy}
                type="button"
                onClick={() => setSelectedStrategy(strategy)}
                className={`strategy-chip${selectedStrategy === strategy ? " active" : ""}`}
              >
                {formatStrategyName(strategy)}
              </button>
            ))}
          </div>
        </div>

        <div className="form-panel signal-panel">
          <div className="form-panel-header">
            <div>
              <h2>Live Signal</h2>
              <p>
                {selectedStrategy
                  ? `${formatStrategyName(selectedStrategy)} is selected.`
                  : "Select a strategy to begin polling."}
              </p>
            </div>
            <span className={`status-pill${hasSignalError ? " error" : ""}`}>
              {loading ? "Updating" : hasSignalError ? "Offline" : "Live"}
            </span>
          </div>

          {hasSignalError && (
            <div className="alert alert-error" role="alert">
              Signal API unavailable. Check that the trading backend is running on port 8000.
            </div>
          )}

          <pre>
            {signal
              ? JSON.stringify(signal, null, 2)
              : "Waiting for the first signal response..."}
          </pre>
        </div>
      </div>
    </section>
  );
}
