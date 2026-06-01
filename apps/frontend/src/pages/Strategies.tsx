import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import SystemHealthWidget from "../components/SystemHealthWidget";
import { useStrategySignals } from "../hooks/useAutoSignals";
import { useUiMode } from "../hooks/useUiMode";
import { formatLocalDateTime, localizeTimestamps } from "../utils/time";

const strategies = [
  "amd",
  "breakout",
  "btst",
  "cbt",
  "crt_tbs",
  "mean_reversion",
  "mtf",
  "mtfa",
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
  return diagnostics[0] ?? "Current market conditions do not meet confirmation criteria.";
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
  return signalRiskRewardValue(signals[0]);
}

function signalRiskRewardValue(signal: any) {
  if (!signal) return 0;
  const explicit = numeric(signal?.rr_ratio ?? signal?.risk_reward ?? signal?.metadata?.rr_ratio, 0);
  if (explicit > 0) return explicit;
  const entry = numeric(signal?.entry_price ?? signal?.entry, 0);
  const stop = numeric(signal?.stop_loss ?? signal?.stop, 0);
  const target = numeric(signal?.target_price ?? signal?.target, 0);
  const risk = Math.abs(entry - stop);
  return risk > 0 ? Math.abs(target - entry) / risk : 0;
}

function signalConfidence(signal: any) {
  return numeric(signal?.score ?? signal?.confidence ?? signal?.confidence_score ?? signal?.metadata?.score ?? signal?.metadata?.confidence, 0);
}

function formatPrice(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed.toFixed(2) : "-";
}

function signalDirection(signal: any, rawSignals: number, hasResponse: boolean) {
  const side = String(signal?.side ?? "").toUpperCase();
  if (side === "BUY" || side === "SELL") return side;
  if (!hasResponse) return "NEUTRAL";
  if (rawSignals > 0) return "WATCHLIST";
  return "REJECTED";
}

function hasHistoricalTrades(backtest: any) {
  return numeric(backtest?.metrics?.total_trades, 0) > 0;
}

function performanceValue(backtest: any, value: unknown, formatter: (value: number) => string) {
  return hasHistoricalTrades(backtest) ? formatter(numeric(value, 0)) : "No trades yet";
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

      <SystemHealthWidget websocketConnected={socketConnected} compact />

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
          const selectedSignal = signals[0] ?? null;
          const tqe = selectedSignal?.trade_qualification ?? {};
          const score = selectedSignal ? signalConfidence(selectedSignal) : signalScore(signals);
          const rr = selectedSignal ? signalRiskRewardValue(selectedSignal) : signalRiskReward(signals);
          const direction = signalDirection(selectedSignal, rawSignals, Boolean(signal));
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

              <div className={`quality-banner quality-${direction.toLowerCase()}`}>
                <strong>{direction}</strong>
                <span>Confidence {score ? score.toFixed(1) : "-"} | RR {rr ? rr.toFixed(2) : "-"}</span>
              </div>

              {hasSignalError && (
                <div className="alert alert-error" role="alert">
                  Signal API unavailable. Check that the trading backend is running on port 8000.
                </div>
              )}

              {!hasSignalError && selectedSignal && (
                <div className="signal-trade-grid">
                  <span>
                    <small>Entry</small>
                    <strong>{formatPrice(selectedSignal.entry_price ?? selectedSignal.entry)}</strong>
                  </span>
                  <span>
                    <small>Stop Loss</small>
                    <strong>{formatPrice(selectedSignal.stop_loss ?? selectedSignal.stop)}</strong>
                  </span>
                  <span>
                    <small>Target</small>
                    <strong>{formatPrice(selectedSignal.target_price ?? selectedSignal.target)}</strong>
                  </span>
                  <span>
                    <small>Risk Reward</small>
                    <strong>{numeric(tqe?.rr, rr) ? numeric(tqe?.rr, rr).toFixed(2) : "-"}</strong>
                  </span>
                  <span>
                    <small>Quality Grade</small>
                    <strong>{selectedSignal.mtfa_grade ?? selectedSignal.quality_grade ?? tqe?.quality_grade ?? selectedSignal.signal_quality ?? "-"}</strong>
                  </span>
                  {selectedSignal.tqe_score !== undefined || tqe?.score !== undefined ? (
                    <span>
                      <small>TQE Score</small>
                      <strong>{selectedSignal.tqe_score ?? tqe?.score}/12</strong>
                    </span>
                  ) : (
                    <span>
                      <small>Confidence</small>
                      <strong>{score ? score.toFixed(1) : "-"}</strong>
                    </span>
                  )}
                  {(selectedSignal.market_context ?? tqe?.market_context) && (
                    <span>
                      <small>Market Context</small>
                      <strong>{selectedSignal.market_context ?? tqe.market_context}</strong>
                    </span>
                  )}
                  {(selectedSignal.volume_status ?? tqe?.volume_status) && (
                    <span>
                      <small>Volume Status</small>
                      <strong>{selectedSignal.volume_status ?? tqe.volume_status}</strong>
                    </span>
                  )}
                  {(selectedSignal.volatility_status ?? tqe?.volatility_status) && (
                    <span>
                      <small>Volatility</small>
                      <strong>{selectedSignal.volatility_status ?? tqe.volatility_status}</strong>
                    </span>
                  )}
                  {(selectedSignal.position_size ?? tqe?.position_sizing?.position_size) && (
                    <span>
                      <small>Position Size</small>
                      <strong>{selectedSignal.position_size ?? tqe.position_sizing.position_size}</strong>
                    </span>
                  )}
                  {(tqe?.position_sizing?.risk_pct || selectedSignal.risk_amount) && (
                    <span>
                      <small>Risk</small>
                      <strong>{tqe?.position_sizing?.risk_pct ?? 1}%</strong>
                    </span>
                  )}
                  {(tqe?.trend_aligned !== undefined) && (
                    <span>
                      <small>Trend</small>
                      <strong>{tqe.trend_aligned ? "Aligned" : "Countertrend"}</strong>
                    </span>
                  )}
                  {selectedSignal.signal_quality && (
                    <span>
                      <small>SMC Quality</small>
                      <strong>{selectedSignal.signal_quality}</strong>
                    </span>
                  )}
                  {selectedSignal.crt_range && (
                    <span>
                      <small>CRT Range</small>
                      <strong>{formatPrice(selectedSignal.crt_range.low)} - {formatPrice(selectedSignal.crt_range.high)}</strong>
                    </span>
                  )}
                  {selectedSignal.liquidity_sweep && (
                    <span>
                      <small>Liquidity Sweep</small>
                      <strong>{selectedSignal.liquidity_sweep.type} @ {formatPrice(selectedSignal.liquidity_sweep.level)}</strong>
                    </span>
                  )}
                  {selectedSignal.trap_type && (
                    <span>
                      <small>Trap Type</small>
                      <strong>{formatStrategyName(String(selectedSignal.trap_type))}</strong>
                    </span>
                  )}
                  {selectedSignal.target_2 && (
                    <span>
                      <small>Target 2</small>
                      <strong>{formatPrice(selectedSignal.target_2)}</strong>
                    </span>
                  )}
                  {selectedSignal.mtfa_4h_trend && (
                    <span>
                      <small>4H Trend</small>
                      <strong>{selectedSignal.mtfa_4h_trend}</strong>
                    </span>
                  )}
                  {selectedSignal.mtfa_4h_zone && (
                    <span>
                      <small>4H Zone</small>
                      <strong>{formatStrategyName(String(selectedSignal.mtfa_4h_zone.zone_type))}</strong>
                    </span>
                  )}
                  {selectedSignal.mtfa_1h_pullback && (
                    <span>
                      <small>1H Pullback</small>
                      <strong>{selectedSignal.mtfa_1h_pullback.reason}</strong>
                    </span>
                  )}
                  {selectedSignal.mtfa_1h_confirmation && (
                    <span>
                      <small>1H Confirmation</small>
                      <strong>{selectedSignal.mtfa_1h_confirmation.score ?? "-"}</strong>
                    </span>
                  )}
                  {selectedSignal.mtfa_15m_trigger && (
                    <span>
                      <small>15M Trigger</small>
                      <strong>{selectedSignal.mtfa_15m_trigger.trigger_type}</strong>
                    </span>
                  )}
                  {selectedSignal.mtfa_score !== undefined && (
                    <span>
                      <small>MTFA Score</small>
                      <strong>{selectedSignal.mtfa_score}/12</strong>
                    </span>
                  )}
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
                  <strong>{performanceValue(backtest, backtestMetrics?.win_rate, (value) => `${value.toFixed(1)}%`)}</strong>
                  Historical win rate
                  <small>{hasHistoricalTrades(backtest) ? "Backtest complete" : "Run backtest to calculate performance."}</small>
                </span>
                <span>
                  <strong>{hasHistoricalTrades(backtest) ? numeric(backtestMetrics?.sharpe_ratio, 0).toFixed(2) : "Backtest not run"}</strong>
                  Sharpe
                  <small>Run backtest to calculate performance.</small>
                </span>
                <span>
                  <strong>{performanceValue(backtest, backtestMetrics?.recent_accuracy ?? backtestMetrics?.win_rate, (value) => `${value.toFixed(1)}%`)}</strong>
                  Recent accuracy
                  <small>{hasHistoricalTrades(backtest) ? "Backtest complete" : "Run backtest to calculate performance."}</small>
                </span>
              </div>

              {!hasSignalError && signal && !hasSignals && (
                <div className="alert alert-warning" role="status">
                  <strong>{direction}:</strong> {noTradeSummary(diagnostics)}
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
