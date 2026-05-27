import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useStrategySignals } from "../hooks/useAutoSignals";
import { useUiMode } from "../hooks/useUiMode";
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
  if (diagnostics.length === 0) return "Current market conditions do not meet confirmation criteria.";
  return "Current market conditions do not meet confirmation criteria.";
}

function numeric(value: unknown, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function signalScore(signals: any[]) {
  const signal = signals[0] ?? {};
  return numeric(signal?.score ?? signal?.confidence ?? signal?.metadata?.score ?? signal?.metadata?.confidence, 0);
}

function signalRiskReward(signals: any[]) {
  const signal = signals[0] ?? {};
  const explicit = numeric(signal?.rr_ratio ?? signal?.risk_reward ?? signal?.metadata?.rr_ratio, 0);
  if (explicit > 0) return explicit;
  const entry = numeric(signal?.entry_price ?? signal?.entry, 0);
  const stop = numeric(signal?.stop_loss ?? signal?.stop, 0);
  const target = numeric(signal?.target_price ?? signal?.target, 0);
  const risk = Math.abs(entry - stop);
  return risk > 0 ? Math.abs(target - entry) / risk : 0;
}

function qualityTier(signals: any[], rawSignals: number) {
  const score = signalScore(signals);
  if (signals.length > 0 && score >= 8) return "HIGH QUALITY";
  if (signals.length > 0 && score >= 6) return "MEDIUM QUALITY";
  if (rawSignals > 0) return "WATCHLIST";
  return "REJECTED";
}

export default function Strategies() {
  const strategyList = useMemo(() => strategies, []);
  const { signalsByStrategy, loading, socketConnected } = useStrategySignals(strategyList, 30000);
  const [backtests, setBacktests] = useState<Record<string, any>>({});
  const uiMode = useUiMode();
  const developerMode = uiMode === "developer";

  useEffect(() => {
    let isMounted = true;
    Promise.all(
      strategyList.map((strategy) =>
        api.backtestStrategy(strategy).then((data) => [strategy, data] as const).catch(() => [strategy, null] as const)
      )
    ).then((entries) => {
      if (isMounted) setBacktests(Object.fromEntries(entries));
    });
    return () => {
      isMounted = false;
    };
  }, [strategyList]);

  return (
    <section className="dashboard-page">
      <div className="page-heading">
        <h1>Strategies</h1>
        <p>{socketConnected ? "Live strategy updates are event-driven." : "WebSocket offline; using conservative fallback refresh."}</p>
      </div>

      <div className="strategy-signal-grid">
        {strategyList.map((strategy) => {
          const signal = signalsByStrategy[strategy];
          const hasSignalError = Boolean(signal?.error);
          const signals = Array.isArray(signal?.data) ? signal.data : [];
          const diagnostics = Array.isArray(signal?.diagnostics) ? signal.diagnostics : [];
          const hasSignals = signals.length > 0;
          const rawSignals = signal?.raw_signals ?? signals.length;
          const freshness = signal?.validation_context;
          const isStale = freshness?.is_recent === false;
          const score = signalScore(signals);
          const rr = signalRiskReward(signals);
          const tier = qualityTier(signals, rawSignals);
          const backtest = backtests[strategy];
          const backtestMetrics = backtest?.metrics ?? {};
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

              <div className={`quality-banner quality-${tier.toLowerCase().replace(" ", "-")}`}>
                <strong>{tier}</strong>
                <span>Confidence {score ? score.toFixed(1) : "-"} | RR {rr ? rr.toFixed(2) : "-"}</span>
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

              <div className="strategy-context">
                <span>
                  <strong>{numeric(backtestMetrics?.win_rate, 0).toFixed(1)}%</strong>
                  Historical win rate
                </span>
                <span>
                  <strong>{numeric(backtestMetrics?.sharpe_ratio, 0).toFixed(2)}</strong>
                  Sharpe
                </span>
                <span>
                  <strong>{numeric(backtestMetrics?.recent_accuracy ?? backtestMetrics?.win_rate, 0).toFixed(1)}%</strong>
                  Recent accuracy
                </span>
              </div>

              {!hasSignalError && signal && !hasSignals && (
                <div className="alert alert-warning" role="status">
                  {noTradeSummary(diagnostics)}
                </div>
              )}

              {!hasSignalError && signal && (
                <div className="diagnostic-list trader-summary" role="status">
                  <div>Data source: {formatMarketSource(signal.market_data?.source)}</div>
                  <div>
                    Latest candle: {formatLocalDateTime(freshness?.latest_candle_at)} | Age {formatAge(freshness?.latest_candle_age_seconds)}
                  </div>
                  <div>Validated {signal.validated_signals ?? 0} of {rawSignals} candidate setups.</div>
                </div>
              )}

              {developerMode && !hasSignalError && (
                <details className="technical-details">
                  <summary>Raw Diagnostics</summary>
                  <div className="diagnostic-list" role="status" aria-label={`${formatStrategyName(strategy)} diagnostics`}>
                    <div>Freshness limit: {formatAge(freshness?.max_candle_age_seconds)}</div>
                    {diagnostics.length === 0 && <div>No diagnostics returned.</div>}
                    {diagnostics.map((item, index) => (
                      <div key={`${strategy}-diagnostic-${index}`}>{item}</div>
                    ))}
                  </div>
                </details>
              )}

              {developerMode && (
                <details className="technical-details">
                  <summary>Raw Signals and API Payload</summary>
                  <pre>
                    {signal
                      ? JSON.stringify(
                        hasSignalError
                          ? localizeTimestamps(signal)
                          : localizeTimestamps({
                            raw_signals: signal.raw_response?.raw_signals ?? signal.raw_signals ?? signals.length,
                            validated_signals: signal.validated_signals ?? signals.length,
                            signals,
                            diagnostics,
                            raw_response: signal.raw_response,
                            validation_context: freshness,
                            market_data: signal.market_data,
                            backtest,
                          }),
                        null,
                        2
                      )
                      : "Waiting for the first signal response..."}
                  </pre>
                </details>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
