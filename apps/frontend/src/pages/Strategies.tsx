import { useMemo } from "react";
import { useStrategySignals } from "../hooks/useAutoSignals";
import { formatLocalDateTime, localizeTimestamps } from "../utils/time";

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

function formatMarketSource(source?: string) {
  if (source === "yahoo-finance") return "Live NIFTY";
  if (source === "stored-live-cache") return "Stored live cache";
  if (source === "sample-fallback") return "Fallback";
  return source ?? "-";
}

function formatAge(seconds?: number | null) {
  if (typeof seconds !== "number" || Number.isNaN(seconds)) return "-";
  const absolute = Math.abs(seconds);
  if (absolute < 60) return `${Math.round(seconds)}s`;
  if (absolute < 3600) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

function noTradeSummary(diagnostics: string[]) {
  if (diagnostics.length === 0) return "No validated signal right now.";
  return diagnostics[0].replace(/\.$/, "");
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
          const diagnostics = Array.isArray(signal?.diagnostics) ? signal.diagnostics : [];
          const hasSignals = signals.length > 0;
          const freshness = signal?.validation_context;
          const isStale = freshness?.is_recent === false;
          const updatedAt = signal?.updated_at
            ? new Date(signal.updated_at).toLocaleTimeString()
            : null;
          const statusLabel = loading && !signal
            ? "Updating"
            : hasSignalError
              ? "Offline"
              : isStale
                ? "Stale"
                : "Live";

          return (
            <div key={strategy} className="form-panel signal-panel strategy-signal-card">
              <div className="form-panel-header">
                <div>
                  <h2>{formatStrategyName(strategy)}</h2>
                  <p>{updatedAt ? `Updated ${updatedAt}` : "Waiting for first refresh."}</p>
                </div>
                <span className={`status-pill${hasSignalError ? " error" : isStale ? " stale" : ""}`}>
                  {statusLabel}
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
                    <strong>{signal.validated_signals ?? signals.length}</strong>
                    Validated
                  </span>
                  <span>
                    <strong>{signal.raw_signals ?? signals.length}</strong>
                    Raw
                  </span>
                </div>
              )}

              {!hasSignalError && signal && !hasSignals && (
                <div className="alert alert-warning" role="status">
                  No trade: {noTradeSummary(diagnostics)}.
                </div>
              )}

              {!hasSignalError && signal && (
                <div className="diagnostic-list" role="status">
                  <div>Data source: {formatMarketSource(signal.market_data?.source)}</div>
                  <div>
                    Latest candle: {formatLocalDateTime(freshness?.latest_candle_at)} | Age {formatAge(freshness?.latest_candle_age_seconds)}
                  </div>
                  <div>Freshness limit: {formatAge(freshness?.max_candle_age_seconds)}</div>
                  <div>Validated {signal.validated_signals ?? 0} of {signal.raw_signals ?? 0} raw setups.</div>
                </div>
              )}

              {!hasSignalError && diagnostics.length > 0 && (
                <div className="diagnostic-list" role="status" aria-label={`${formatStrategyName(strategy)} diagnostics`}>
                  {diagnostics.slice(0, 4).map((item, index) => (
                    <div key={`${strategy}-diagnostic-${index}`}>{item}</div>
                  ))}
                </div>
              )}

              <pre>
                {signal
                  ? JSON.stringify(
                    hasSignalError
                      ? localizeTimestamps(signal)
                      : localizeTimestamps({ signals, diagnostics, validation_context: freshness }),
                    null,
                    2
                  )
                  : "Waiting for the first signal response..."}
              </pre>
            </div>
          );
        })}
      </div>
    </section>
  );
}
