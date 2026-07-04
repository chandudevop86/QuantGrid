import { useEffect, useState, type CSSProperties } from "react";

import { api } from "../api";
import Loader from "../components/Loader";
import { hasAuthToken } from "../roles";
import { createSocket } from "../socket";
import { getMarketStatusClass, getMarketStatusLabel } from "../utils/marketStatus";

type Decision = {
  market_bias?: "Bullish" | "Bearish" | "Neutral" | string;
  trade_recommendation?: "Buy CE" | "Buy PE" | "No Trade" | string;
  confidence?: number;
  entry_zone?: string;
  stop_loss?: string;
  target?: string;
  risk_level?: string;
  support?: string;
  resistance?: string;
  simple_explanation?: string;
  system_status?: string;
  invalidation_level?: string;
  supporting_factors?: string[];
  opposing_factors?: string[];
  warnings?: string[];
  score_reason?: string;
  data_status?: string;
  recommendation_metrics?: Record<string, any>;
  factor_snapshot?: {
    final_decision?: {
      trade_decision?: string;
      strategy?: string;
      trade_quality?: string;
      confidence_score?: number;
      probability_score?: number;
      confluence_score?: number;
      entry_zone?: string;
      stop_loss?: string;
      target?: string;
      risk_reward_ratio?: number | null;
      position_size?: number | null;
      risk_level?: string;
      explanation?: string[];
      invalidation_level?: string;
      system_status?: string;
      block_reasons?: string[];
      strategy_selection?: { selected_strategy?: string; selected_score?: number; reason?: string };
      probability_engine?: { probability_score?: number; confidence_score?: number; reason?: string };
      no_trade_intelligence?: { primary_reason?: string; block_reasons?: string[]; wait_for?: string[] };
      explainability?: { plain_english?: string; score_reason?: string; warnings?: string[] };
    };
    checklist_score?: number;
    checklist?: {
      checklist_score?: number;
      passed?: string[];
      failed?: string[];
      warnings?: string[];
      trend?: { trend_direction?: string; trend_strength?: number; warning_if_sideways?: string };
      ema?: { ema_bias?: string; ema_strength?: number; reason?: string; warning?: string };
      volume?: { volume_status?: string; volume_strength?: number; supports_trade?: boolean; reason?: string };
      support_resistance?: { support?: number; resistance?: number; entry_zone?: string; invalidation_level?: string; warning?: string };
      risk_reward?: { risk_reward_ratio?: number; position_size?: number; allowed?: boolean; warnings?: string[] };
      htf?: { allowed_direction?: string; passed?: boolean; reason?: string };
      market_structure?: { structure_bias?: string; latest_structure_event?: string; reason?: string };
      supply_demand?: { trade_location_quality?: string; nearest_demand?: number; nearest_supply?: number; warning?: string };
      fvg?: { type?: string; passed?: boolean; reason?: string };
      price_action?: { pattern?: string; confirmed?: boolean; reason?: string };
      options_flow?: { bias?: string; passed?: boolean; reason?: string };
      institutional?: { bias?: string; institutional_score?: number; passed?: boolean; reason?: string };
      discipline?: { passed?: boolean; discipline_passed?: boolean; reason?: string; blocked_reasons?: string[] };
      market_regime?: { regime?: string; market_regime?: string; regime_risk?: string; regime_strength?: string; allowed_strategy_type?: string; allowed_strategies?: string[]; warning?: string };
      strategy_selection?: { selected_strategy?: string; selected_score?: number; reason?: string };
      confidence_engine?: { confidence_score?: number };
      confluence_engine?: { confluence_score?: number; trade_quality?: string };
    };
    trend_analysis?: { trend_direction?: string; trend_strength?: number; warning_if_sideways?: string };
    ema_analysis?: { ema_bias?: string; ema_strength?: number; reason?: string; warning?: string };
    volume_analysis?: { volume_status?: string; volume_strength?: number; supports_trade?: boolean; reason?: string };
    support_resistance?: { support?: number; resistance?: number; entry_zone?: string; invalidation_level?: string; warning?: string };
    risk_reward?: { risk_reward_ratio?: number; position_size?: number; allowed?: boolean; warnings?: string[] };
    high_probability_trade_engine?: {
      paper_trade_allowed?: boolean;
      paper_trade_gate?: { allowed?: boolean; status?: string; reasons?: string[] };
      layers?: Record<string, any>;
    };
  };
};

function formatMoney(value: unknown) {
  const numeric = Number(value ?? 0);
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(Number.isFinite(numeric) ? numeric : 0);
}

function formatTime(value: unknown) {
  if (!value) return "-";
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? "-" : date.toLocaleTimeString();
}

function confidenceTone(confidence: number) {
  if (confidence >= 70) return "good";
  if (confidence >= 45) return "warn";
  return "danger";
}

function optionsRead(bias: string) {
  if (bias === "Bullish") return "Options positioning supports bulls.";
  if (bias === "Bearish") return "Options positioning supports bears.";
  return "Options positioning does not justify a trade.";
}

function valueOrWaiting(value: unknown) {
  if (value === null || value === undefined || value === "") return "Waiting";
  return String(value);
}

function badgeTone(value: unknown) {
  const text = String(value ?? "").toLowerCase();
  if (text.includes("bull") || text.includes("buy") || text.includes("live") || text.includes("pass") || text.includes("good") || text.includes("excellent")) return "good";
  if (text.includes("bear") || text.includes("fail") || text.includes("block") || text.includes("poor") || text.includes("risk")) return "danger";
  if (text.includes("stale") || text.includes("closed") || text.includes("wait") || text.includes("average") || text.includes("warning")) return "warn";
  return "muted";
}

function checklistStatus(passed?: boolean, warning?: string | null) {
  if (warning) return "Warning";
  if (passed === true) return "Pass";
  if (passed === false) return "Fail";
  return "Warning";
}

function fallbackDecision(): Decision {
  return {
    market_bias: "Neutral",
    trade_recommendation: "No Trade",
    confidence: 0,
    entry_zone: "Waiting for market data",
    stop_loss: "Not applicable",
    target: "Not applicable",
    risk_level: "Low",
    support: "Nearest confirmed demand zone",
    resistance: "Nearest confirmed supply zone",
    simple_explanation: "Login and wait for a clean market read.",
    system_status: "Checking",
    invalidation_level: "No active view",
    supporting_factors: [],
    opposing_factors: [],
    warnings: [],
    score_reason: "Waiting for the decision pipeline.",
    data_status: "Checking",
  };
}

export default function Dashboard() {
  const [operations, setOperations] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(hasAuthToken());
  const [socketStatus, setSocketStatus] = useState<"online" | "offline" | "polling">("offline");

  useEffect(() => {
    const syncAuth = () => setIsAuthenticated(hasAuthToken());
    window.addEventListener("quantgrid-role-change", syncAuth);
    window.addEventListener("storage", syncAuth);
    return () => {
      window.removeEventListener("quantgrid-role-change", syncAuth);
      window.removeEventListener("storage", syncAuth);
    };
  }, []);

  useEffect(() => {
    if (!isAuthenticated) {
      setOperations(null);
      setLoading(false);
      return;
    }

    let active = true;
    let socket: WebSocket | null = null;
    let fallbackId: number | null = null;

    const load = async () => {
      try {
        const data = await api.operationsStatus();
        if (!active) return;
        setOperations(data);
        setError(null);
      } catch {
        if (active) setError("Dashboard API is not available yet.");
      } finally {
        if (active) setLoading(false);
      }
    };

    const startFallback = () => {
      if (fallbackId !== null) return;
      setSocketStatus("polling");
      fallbackId = window.setInterval(load, 15000);
    };

    void load();
    socket = createSocket();
    socket.onopen = () => {
      setSocketStatus("online");
      if (fallbackId !== null) {
        window.clearInterval(fallbackId);
        fallbackId = null;
      }
    };
    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message?.type === "dashboard_status" && message?.payload) {
          setOperations(message.payload);
        }
      } catch {
        setError("Received an invalid dashboard status update.");
      }
    };
    socket.onerror = () => socket?.close();
    socket.onclose = () => {
      if (!active) return;
      setSocketStatus("offline");
      startFallback();
    };

    return () => {
      active = false;
      if (fallbackId !== null) window.clearInterval(fallbackId);
      socket?.close();
    };
  }, [isAuthenticated]);

  const decision = { ...fallbackDecision(), ...(operations?.decision ?? {}) };
  const confidence = Number(decision.confidence ?? 0);
  const market = operations?.market_status;
  const risk = operations?.risk_summary;
  const health = operations?.system_health;
  const marketStatusLabel = getMarketStatusLabel(market);
  const checklist = decision.factor_snapshot?.checklist;
  const checklistTrend = checklist?.trend ?? decision.factor_snapshot?.trend_analysis;
  const checklistEma = checklist?.ema ?? decision.factor_snapshot?.ema_analysis;
  const checklistVolume = checklist?.volume ?? decision.factor_snapshot?.volume_analysis;
  const checklistSr = checklist?.support_resistance ?? decision.factor_snapshot?.support_resistance;
  const checklistRr = checklist?.risk_reward ?? decision.factor_snapshot?.risk_reward;
  const finalDecision = decision.factor_snapshot?.final_decision;
  const paperGate = decision.factor_snapshot?.high_probability_trade_engine?.paper_trade_gate;
  const disciplinePass = checklist?.discipline?.discipline_passed ?? checklist?.discipline?.passed;
  const plainReason = finalDecision?.explainability?.plain_english ?? finalDecision?.explanation?.[0] ?? decision.simple_explanation;
  const supplyDemandText = checklist?.supply_demand?.trade_location_quality
    ? `${checklist.supply_demand.trade_location_quality} location`
    : "Unknown";
  const riskStatus = paperGate?.allowed ? "Paper trade allowed" : paperGate?.status ? `Paper trade ${paperGate.status.toLowerCase()}` : finalDecision?.risk_level ?? decision.risk_level;
  const marketSnapshot = [
    { label: "NIFTY", value: finalDecision?.trade_decision ?? decision.trade_recommendation, tone: badgeTone(finalDecision?.trade_decision ?? decision.trade_recommendation) },
    { label: "BANK NIFTY", value: "Waiting", tone: "muted" },
    { label: "FIN NIFTY", value: "Waiting", tone: "muted" },
    { label: "GIFT NIFTY", value: valueOrWaiting(decision.factor_snapshot?.gift_nifty_bias), tone: badgeTone(decision.factor_snapshot?.gift_nifty_bias) },
    { label: "India VIX", value: valueOrWaiting(decision.factor_snapshot?.india_vix), tone: Number(decision.factor_snapshot?.india_vix ?? 0) >= 22 ? "danger" : "good" },
    { label: "USDINR", value: "Waiting", tone: "muted" },
    { label: "Crude", value: "Waiting", tone: "muted" },
    { label: "US Futures", value: "Waiting", tone: "muted" },
    { label: "Market", value: marketStatusLabel, tone: badgeTone(marketStatusLabel) },
  ];
  const checklistRows = [
    { label: "Trend", status: checklistStatus(checklistTrend?.trend_direction !== "SIDEWAYS", checklistTrend?.warning_if_sideways), reason: checklistTrend?.supporting_evidence?.[0] ?? "Trend read unavailable.", weight: "15" },
    { label: "Higher Timeframe", status: checklistStatus(checklist?.htf?.passed), reason: checklist?.htf?.reason ?? "HTF read unavailable.", weight: "15" },
    { label: "Market Structure", status: checklistStatus(checklist?.market_structure?.structure_bias !== "Neutral", checklist?.market_structure?.warning), reason: checklist?.market_structure?.reason ?? "Structure read unavailable.", weight: "15" },
    { label: "Support / Resistance", status: checklistStatus(!checklistSr?.warning, checklistSr?.warning), reason: checklistSr?.warning ?? "Support and resistance are usable.", weight: "10" },
    { label: "Price Action", status: checklistStatus(checklist?.price_action?.confirmed), reason: checklist?.price_action?.reason ?? "Price action read unavailable.", weight: "10" },
    { label: "Volume", status: checklistStatus(checklistVolume?.supports_trade), reason: checklistVolume?.reason ?? "Volume read unavailable.", weight: "10" },
    { label: "Options Flow", status: checklistStatus(checklist?.options_flow?.passed, checklist?.options_flow?.warning), reason: checklist?.options_flow?.reason ?? "Options read unavailable.", weight: "10" },
    { label: "Institutional Flow", status: checklistStatus(checklist?.institutional?.passed, checklist?.institutional?.warning), reason: checklist?.institutional?.reason ?? "Institutional read unavailable.", weight: "10" },
    { label: "Risk", status: checklistStatus(checklistRr?.allowed), reason: checklistRr?.allowed ? "Risk reward is acceptable." : "Risk reward needs review.", weight: "10" },
    { label: "Discipline", status: checklistStatus(Boolean(disciplinePass), checklist?.discipline?.blocked_reasons?.[0]), reason: checklist?.discipline?.reason ?? "Discipline read unavailable.", weight: "10" },
  ];
  const regimeRows = ["NIFTY", "BANK NIFTY", "FIN NIFTY"].map((instrument, index) => ({
    instrument,
    regime: index === 0 ? checklist?.market_regime?.market_regime ?? checklist?.market_regime?.regime ?? "Unknown" : "Waiting",
    bias: index === 0 ? decision.market_bias : "Waiting",
    strength: index === 0 ? checklist?.market_regime?.regime_strength ?? "Unknown" : "Waiting",
    strategy: index === 0 ? checklist?.market_regime?.allowed_strategy_type ?? "Wait" : "Waiting",
    warning: index === 0 ? checklist?.market_regime?.warning : "Awaiting backend snapshot.",
  }));
  const whatWouldChange = finalDecision?.no_trade_intelligence?.wait_for ?? ["A clean pullback inside the entry zone."];

  return (
    <section className="dashboard-page decision-dashboard">
      <div className="page-heading dashboard-heading">
        <div>
          <h1>QuantGrid</h1>
          <p>In less than 30 seconds: Buy CE, Buy PE, or No Trade.</p>
        </div>
        <span className={`decision-status decision-status-${String(decision.system_status).toLowerCase()}`}>
          {decision.system_status}
        </span>
      </div>

      {!isAuthenticated && (
        <div className="alert alert-warning" role="status">
          Login with an authorized account to view today&apos;s trading decision.
        </div>
      )}

      {isAuthenticated && loading && <Loader label="Reading market..." />}
      {isAuthenticated && loading && (
        <div className="skeleton-grid" aria-hidden="true">
          <div className="skeleton-card" />
          <div className="skeleton-card" />
          <div className="skeleton-card" />
        </div>
      )}
      {error && <p className="error-text">{error}</p>}

      {isAuthenticated && !loading && !error && (
        <>
          <div className="market-snapshot-bar" aria-label="Market overview">
            {marketSnapshot.map((item) => (
              <span className={`market-snapshot-item market-snapshot-${item.tone}`} key={item.label}>
                <small>{item.label}</small>
                <strong>{item.value}</strong>
              </span>
            ))}
          </div>

          <article className={`decision-card decision-card-${badgeTone(finalDecision?.trade_decision ?? decision.trade_recommendation)}`}>
            <div className="decision-copy">
              <span className="decision-kicker">Today&apos;s Decision</span>
              <strong>{finalDecision?.trade_decision ?? decision.trade_recommendation}</strong>
              <p>{plainReason}</p>
            </div>
            <div className={`confidence-card confidence-${confidenceTone(confidence)}`}>
              <span>Confidence</span>
              <strong>{confidence}%</strong>
              <div className="confidence-track" style={{ "--confidence": `${confidence}%` } as CSSProperties}>
                <span />
              </div>
            </div>
          </article>

          <div className="decision-grid">
            <span><small>Trade Quality</small><strong>{finalDecision?.trade_quality ?? "Skip"}</strong></span>
            <span><small>Strategy</small><strong>{finalDecision?.strategy ?? finalDecision?.strategy_selection?.selected_strategy ?? "none"}</strong></span>
            <span><small>Market Regime</small><strong>{checklist?.market_regime?.market_regime ?? checklist?.market_regime?.regime ?? "Unknown"}</strong></span>
            <span><small>Probability</small><strong>{Number(finalDecision?.probability_score ?? finalDecision?.confidence_score ?? confidence)}%</strong></span>
            <span><small>Confluence Score</small><strong>{Number(finalDecision?.confluence_score ?? checklist?.confluence_engine?.confluence_score ?? 0)}%</strong></span>
            <span><small>Entry</small><strong>{finalDecision?.entry_zone ?? decision.entry_zone}</strong></span>
            <span><small>Stop Loss</small><strong>{finalDecision?.stop_loss ?? decision.stop_loss}</strong></span>
            <span><small>Target</small><strong>{finalDecision?.target ?? decision.target}</strong></span>
            <span><small>Risk/Reward</small><strong>{Number(finalDecision?.risk_reward_ratio ?? checklistRr?.risk_reward_ratio ?? 0).toFixed(2)}</strong></span>
            <span><small>Position Size</small><strong>{finalDecision?.position_size ?? checklistRr?.position_size ?? 0}</strong></span>
            <span><small>Risk Status</small><strong>{riskStatus}</strong></span>
            <span><small>Support</small><strong>{decision.support}</strong></span>
            <span><small>Resistance</small><strong>{decision.resistance}</strong></span>
            <span><small>Invalidation Level</small><strong>{finalDecision?.invalidation_level ?? decision.invalidation_level}</strong></span>
            <span><small>System Status</small><strong>{finalDecision?.system_status ?? decision.data_status}</strong></span>
          </div>

          <div className="status-panel-grid compact-status-grid">
            <div className="status-panel">
              <div className="status-panel-header">
                <span>Supporting</span>
                <strong>{decision.supporting_factors?.length ?? 0}</strong>
              </div>
              <div className="status-panel-body">
                {(decision.supporting_factors?.length ? decision.supporting_factors : ["No strong supporting factors yet."]).slice(0, 4).map((item) => (
                  <span key={item}>{item}</span>
                ))}
              </div>
            </div>

            <div className="status-panel">
              <div className="status-panel-header">
                <span>Opposing</span>
                <strong>{decision.opposing_factors?.length ?? 0}</strong>
              </div>
              <div className="status-panel-body">
                {(decision.opposing_factors?.length ? decision.opposing_factors : ["No major opposing factor."]).slice(0, 4).map((item) => (
                  <span key={item}>{item}</span>
                ))}
              </div>
            </div>

            <div className="status-panel">
              <div className="status-panel-header">
                <span>Warnings</span>
                <strong>{decision.warnings?.length ?? 0}</strong>
              </div>
              <div className="status-panel-body">
                {(decision.warnings?.length ? decision.warnings : ["No active warning."]).slice(0, 4).map((item) => (
                  <span key={item}>{item}</span>
                ))}
              </div>
            </div>
          </div>

          <div className="dashboard-section">
            <div className="section-header">
              <h2>Decision Quality</h2>
              <span>{decision.score_reason}</span>
            </div>
            <div className="execution-safety-grid">
              <span><small>Precision</small><strong>{Math.round(Number(decision.recommendation_metrics?.precision ?? 0) * 100)}%</strong></span>
              <span><small>Recall</small><strong>{Math.round(Number(decision.recommendation_metrics?.recall ?? 0) * 100)}%</strong></span>
              <span><small>Trade Quality</small><strong>{finalDecision?.trade_quality ?? "Skip"}</strong></span>
              <span><small>Confluence</small><strong>{Number(finalDecision?.confluence_score ?? checklist?.confluence_engine?.confluence_score ?? 0)}%</strong></span>
              <span><small>Skipped Trades</small><strong>{Number(decision.recommendation_metrics?.skipped_trades ?? 0)}</strong></span>
              <span><small>Blocked Trades</small><strong>{Number(decision.recommendation_metrics?.blocked_trades ?? 0)}</strong></span>
              <span><small>Profit Factor</small><strong>{Number(decision.recommendation_metrics?.profit_factor ?? 0).toFixed(2)}</strong></span>
              <span><small>Max Drawdown</small><strong>{formatMoney(decision.recommendation_metrics?.max_drawdown)}</strong></span>
            </div>
          </div>

          <div className="dashboard-section narrative-section">
            <div className="section-header">
              <h2>Market Narrative</h2>
              <span>{finalDecision?.explainability?.score_reason ?? decision.score_reason}</span>
            </div>
            <div className="narrative-card">
              <p>{plainReason}</p>
              <div className="narrative-columns">
                <div>
                  <strong>Supporting Factors</strong>
                  {(decision.supporting_factors?.length ? decision.supporting_factors : ["No strong supporting factors yet."]).slice(0, 4).map((item) => <span key={item}>{item}</span>)}
                </div>
                <div>
                  <strong>Counter Reasons</strong>
                  {(decision.opposing_factors?.length ? decision.opposing_factors : ["No major opposing factor."]).slice(0, 4).map((item) => <span key={item}>{item}</span>)}
                </div>
                <div>
                  <strong>What Changes The View</strong>
                  {whatWouldChange.slice(0, 4).map((item) => <span key={item}>{item}</span>)}
                </div>
              </div>
            </div>
          </div>

          <div className="status-panel-grid regime-grid">
            {regimeRows.map((row) => (
              <div className="status-panel regime-card" key={row.instrument}>
                <div className="status-panel-header">
                  <span>{row.instrument}</span>
                  <strong>{row.regime}</strong>
                </div>
                <div className="status-panel-body">
                  <span>Bias: {row.bias}</span>
                  <span>Strength: {row.strength}</span>
                  <span>Allowed strategy: {row.strategy}</span>
                  <span>{row.warning || "No active regime warning."}</span>
                </div>
              </div>
            ))}
          </div>

          <div className="dashboard-section">
            <div className="section-header">
              <h2>30-Second Checklist</h2>
              <span>Checklist Score: {Number(checklist?.checklist_score ?? decision.factor_snapshot?.checklist_score ?? 0)}%</span>
            </div>
            <div className="checklist-panel">
              {checklistRows.map((row) => (
                <div className="checklist-row" key={row.label}>
                  <span className={`status-pill status-pill-${badgeTone(row.status)}`}>{row.status}</span>
                  <strong>{row.label}</strong>
                  <p>{row.reason}</p>
                  <small>{row.weight} pts</small>
                </div>
              ))}
            </div>
          </div>

          <div className="status-panel-grid compact-status-grid">
            <div className="status-panel">
              <div className="status-panel-header">
                <span>Market</span>
                <strong className={`market-status-text ${getMarketStatusClass(marketStatusLabel)}`}>
                  {marketStatusLabel}
                </strong>
              </div>
              <div className="status-panel-body">
                <span>Session: {market?.session_state ?? "unknown"}</span>
                <span>Feed delay: {market?.feed_delay_seconds ?? "-"}s</span>
                <span>Last candle: {formatTime(market?.last_candle_timestamp)}</span>
              </div>
            </div>

            <div className="status-panel">
              <div className="status-panel-header">
                <span>Signal</span>
                <strong>{decision.market_bias}</strong>
              </div>
              <div className="status-panel-body">
                <span>{optionsRead(String(decision.market_bias))}</span>
                <span>Recommendation: {decision.trade_recommendation}</span>
                <span>Wait when confidence is below 70%.</span>
              </div>
            </div>

            <div className="status-panel">
              <div className="status-panel-header">
                <span>System</span>
                <strong>{decision.system_status}</strong>
              </div>
              <div className="status-panel-body">
                <span>Mode: {risk?.execution_mode ?? "PAPER"}</span>
                <span>Risk state: {risk?.active_risk_state ?? "UNKNOWN"}</span>
                <span>Daily PnL: {formatMoney(risk?.daily_pnl)}</span>
                <span>Realtime: {socketStatus}</span>
              </div>
            </div>
          </div>

          <div className="dashboard-section">
            <div className="section-header">
              <h2>System Status</h2>
              <span>Only what affects the decision</span>
            </div>
            <div className="execution-safety-grid">
              <span><small>API</small><strong>{health?.api?.healthy ? "Ready" : "Review"}</strong></span>
              <span><small>Database</small><strong>{health?.db?.healthy ? "Ready" : "Review"}</strong></span>
              <span><small>Market Data</small><strong>{health?.market_data?.healthy ? "Usable" : "Waiting"}</strong></span>
              <span><small>Broker</small><strong>{health?.broker?.connected ? "Connected" : "Paper"}</strong></span>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
