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
  recommendation_metrics?: Record<string, number>;
  factor_snapshot?: {
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
    };
    trend_analysis?: { trend_direction?: string; trend_strength?: number; warning_if_sideways?: string };
    ema_analysis?: { ema_bias?: string; ema_strength?: number; reason?: string; warning?: string };
    volume_analysis?: { volume_status?: string; volume_strength?: number; supports_trade?: boolean; reason?: string };
    support_resistance?: { support?: number; resistance?: number; entry_zone?: string; invalidation_level?: string; warning?: string };
    risk_reward?: { risk_reward_ratio?: number; position_size?: number; allowed?: boolean; warnings?: string[] };
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
      {error && <p className="error-text">{error}</p>}

      {isAuthenticated && !loading && !error && (
        <>
          <article className="decision-card">
            <div className="decision-copy">
              <span className="decision-kicker">{decision.market_bias} Bias</span>
              <strong>{decision.trade_recommendation}</strong>
              <p>{decision.simple_explanation}</p>
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
            <span><small>Entry Zone</small><strong>{decision.entry_zone}</strong></span>
            <span><small>Stop Loss</small><strong>{decision.stop_loss}</strong></span>
            <span><small>Target</small><strong>{decision.target}</strong></span>
            <span><small>Risk Level</small><strong>{decision.risk_level}</strong></span>
            <span><small>Support</small><strong>{decision.support}</strong></span>
            <span><small>Resistance</small><strong>{decision.resistance}</strong></span>
            <span><small>Invalidation</small><strong>{decision.invalidation_level}</strong></span>
            <span><small>Data</small><strong>{decision.data_status}</strong></span>
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
              <span><small>Profit Factor</small><strong>{Number(decision.recommendation_metrics?.profit_factor ?? 0).toFixed(2)}</strong></span>
              <span><small>Max Drawdown</small><strong>{formatMoney(decision.recommendation_metrics?.max_drawdown)}</strong></span>
            </div>
          </div>

          <div className="dashboard-section">
            <div className="section-header">
              <h2>30-Second Checklist</h2>
              <span>Checklist Score: {Number(checklist?.checklist_score ?? decision.factor_snapshot?.checklist_score ?? 0)}%</span>
            </div>
            <div className="execution-safety-grid">
              <span><small>Trend</small><strong>{checklistTrend?.trend_direction ?? "Unknown"}</strong></span>
              <span><small>EMA</small><strong>{checklistEma?.ema_bias ?? "Unknown"}</strong></span>
              <span><small>Volume</small><strong>{checklistVolume?.volume_status ?? "Unknown"}</strong></span>
              <span><small>Risk Reward</small><strong>{Number(checklistRr?.risk_reward_ratio ?? 0).toFixed(2)}</strong></span>
            </div>
            <div className="status-panel-body">
              <span>{checklistEma?.reason ?? "EMA read unavailable."}</span>
              <span>{checklistVolume?.reason ?? "Volume read unavailable."}</span>
              <span>{checklistSr?.warning ?? "Support and resistance are acceptable."}</span>
              <span>{checklistRr?.allowed ? "Risk reward is acceptable." : "Risk reward needs review."}</span>
              {(checklist?.passed ?? []).slice(0, 2).map((item) => <span key={item}>{item}</span>)}
              {(checklist?.failed ?? []).slice(0, 2).map((item) => <span key={item}>No Trade: {item}</span>)}
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
