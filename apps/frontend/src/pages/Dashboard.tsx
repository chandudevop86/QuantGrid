import { useEffect, useState, type CSSProperties } from "react";

import Loader from "../components/Loader";
import { useOperationsStatus } from "../context/OperationsStatusContext";
import { hasAuthToken } from "../roles";
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
      selected_strategy?: string;
      strategy_version?: string;
      strategy?: string;
      trade_quality?: string;
      confidence_score?: number;
      probability_score?: number;
      confidence_label?: string;
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
      trade_eligibility?: { eligible?: boolean; mode?: string; status?: string; reasons?: string[] };
      trade_plan?: { decision?: string; entry_zone?: string; stop_loss?: string; target?: string; invalidation_level?: string; risk_reward_ratio?: number | null; position_size?: number | null } | null;
      trade_confidence?: { score?: number; label?: string; meaning?: string; factors?: Array<{ name?: string; contribution?: number; weight?: number; source?: string; timestamp?: string; available?: boolean }> };
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
  const { operations, loading, error, socketStatus } = useOperationsStatus();
  const [isAuthenticated, setIsAuthenticated] = useState(hasAuthToken());

  useEffect(() => {
    const syncAuth = () => setIsAuthenticated(hasAuthToken());
    window.addEventListener("quantgrid-role-change", syncAuth);
    window.addEventListener("storage", syncAuth);
    return () => {
      window.removeEventListener("quantgrid-role-change", syncAuth);
      window.removeEventListener("storage", syncAuth);
    };
  }, []);

  const decision = { ...fallbackDecision(), ...(operations?.decision ?? {}) };
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
  const confidence = Number(finalDecision?.trade_confidence?.score ?? decision.confidence ?? 0);
  const paperGate = decision.factor_snapshot?.high_probability_trade_engine?.paper_trade_gate;
  const dataQuality = decision.factor_snapshot?.data_quality ?? checklist?.data_quality;
  const tradeEligible = Boolean(
    finalDecision?.trade_eligibility?.eligible
    ?? (paperGate?.allowed
    && dataQuality?.usable_for_trade
    && (finalDecision?.trade_decision ?? decision.trade_recommendation) !== "No Trade")
  );
  const noTradeReasons = (
    finalDecision?.block_reasons?.length
      ? finalDecision.block_reasons
      : dataQuality?.critical_errors?.length
        ? dataQuality.critical_errors
        : decision.warnings?.length
          ? decision.warnings
          : ["Conditions do not align for a qualified trade."]
  );
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
          <span className="page-eyebrow">{isAuthenticated ? "Market intelligence" : "Risk-first NIFTY options"}</span>
          <h1>{isAuthenticated ? "Decision overview" : "Trade with discipline, not impulse."}</h1>
          <p>{isAuthenticated ? "A focused view of today's setup, confidence, risk, and execution readiness." : "One explainable decision workspace for Buy CE, Buy PE, or No Trade—with risk checks before execution."}</p>
        </div>
        <span className={`decision-status decision-status-${String(decision.system_status).toLowerCase()}`}>
          {decision.system_status}
        </span>
      </div>

      {!isAuthenticated && (
        <>
          <section className="guest-hero-panel" aria-label="QuantGrid product overview">
            <div className="guest-hero-copy">
              <span className="guest-proof-label"><i aria-hidden="true" /> Decision-first trading workspace</span>
              <h2>Clarity before every options decision.</h2>
              <p>QuantGrid brings market context, confirmation, position risk, and execution readiness into one disciplined workflow.</p>
              <div className="guest-hero-actions">
                <a className="guest-primary-action" href="#quantgrid-login">Open your workspace</a>
                <span>Authorized access only</span>
              </div>
            </div>
            <div className="guest-decision-preview" aria-label="Example decision output">
              <div className="guest-preview-head"><span>Decision framework</span><strong>Risk first</strong></div>
              <div className="guest-preview-decision"><small>Possible outcome</small><strong>BUY CE · BUY PE · NO TRADE</strong></div>
              <div className="guest-preview-grid">
                <span><small>Context</small><strong>Market regime</strong></span>
                <span><small>Evidence</small><strong>Confluence</strong></span>
                <span><small>Protection</small><strong>Risk gates</strong></span>
                <span><small>Clarity</small><strong>Explainability</strong></span>
              </div>
            </div>
          </section>

          <section className="guest-section">
            <div className="guest-section-heading"><span>One focused workflow</span><h2>From market data to a disciplined decision</h2></div>
            <div className="guest-workflow" aria-label="QuantGrid workflow">
              {[
                ["01", "Read", "Market regime and data freshness"],
                ["02", "Confirm", "Trend, structure, volume, and options context"],
                ["03", "Qualify", "Confidence, confluence, and trade quality"],
                ["04", "Protect", "Entry, stop, target, and exposure checks"],
                ["05", "Review", "Paper execution and auditable outcomes"],
              ].map(([number, title, copy]) => <article key={number}><span>{number}</span><strong>{title}</strong><p>{copy}</p></article>)}
            </div>
          </section>

          <section className="guest-section guest-principles-section">
            <div className="guest-section-heading"><span>Built for discipline</span><h2>Fewer decisions. Better explained.</h2></div>
            <div className="guest-principles-grid">
              <article><strong>No Trade is a decision</strong><p>QuantGrid can withhold a setup when confirmation, freshness, or risk requirements are not satisfied.</p></article>
              <article><strong>Risk before execution</strong><p>Position sizing, loss limits, exposure, and execution readiness remain visible before an order is considered.</p></article>
              <article><strong>Evidence over prediction</strong><p>Supporting factors, opposing factors, warnings, and invalidation levels explain what could change the view.</p></article>
            </div>
          </section>

          <aside className="guest-disclaimer">
            <strong>Decision support, not a profit promise.</strong>
            <p>QuantGrid assists structured analysis and risk management. Markets are uncertain, and no software can guarantee profitable trades. Validate decisions and use paper mode before live execution.</p>
          </aside>
        </>
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
          <section className="product-dashboard-section" aria-labelledby="market-decision-title">
            <div className="section-header"><div><span className="section-number">01</span><h2 id="market-decision-title">Market Decision</h2></div><span>Updated {formatTime(operations?.updated_at)}</span></div>
            <div className="market-snapshot-bar" aria-label="Available market overview">
              {marketSnapshot.filter((item) => item.value !== "Waiting").map((item) => <span className={`market-snapshot-item market-snapshot-${item.tone}`} key={item.label}><small>{item.label}</small><strong>{item.value}</strong></span>)}
            </div>
            <article className={`decision-card decision-card-${badgeTone(finalDecision?.trade_decision ?? decision.trade_recommendation)}`}>
              <div className="decision-copy"><span className="decision-kicker">Current classification</span><strong>{finalDecision?.trade_decision ?? decision.trade_recommendation}</strong><p>{plainReason}</p></div>
              <div className={`confidence-card confidence-${confidenceTone(confidence)}`}><span>Trade Confidence</span><strong>{confidence}%</strong><div className="confidence-track" style={{ "--confidence": `${confidence}%` } as CSSProperties}><span /></div></div>
            </article>
            <div className="decision-grid decision-grid-compact">
              <span><small>Market Bias</small><strong>{decision.market_bias}</strong></span>
              <span><small>Signal Quality</small><strong>{finalDecision?.trade_quality ?? "Skip"}</strong></span>
              <span><small>Market Regime</small><strong>{checklist?.market_regime?.market_regime ?? checklist?.market_regime?.regime ?? "Unknown"}</strong></span>
              <span><small>Data Freshness</small><strong>{dataQuality?.status ?? decision.data_status}</strong></span>
            </div>
          </section>

          <section className="product-dashboard-section" aria-labelledby="why-decision-title">
            <div className="section-header"><div><span className="section-number">02</span><h2 id="why-decision-title">Why This Decision</h2></div><span>Evidence, conflicts, and what changes the view</span></div>
            <div className="narrative-card"><p>{plainReason}</p><div className="narrative-columns">
              <div><strong>Supporting Evidence</strong>{(decision.supporting_factors?.length ? decision.supporting_factors : ["No verified supporting evidence."]).slice(0, 5).map((item) => <span key={item}>{item}</span>)}</div>
              <div><strong>Opposing & Missing</strong>{([...decision.opposing_factors, ...decision.warnings].length ? [...decision.opposing_factors, ...decision.warnings] : ["No active conflict."]).slice(0, 5).map((item) => <span key={item}>{item}</span>)}</div>
              <div><strong>What Changes The View</strong>{whatWouldChange.slice(0, 5).map((item) => <span key={item}>{item}</span>)}</div>
            </div></div>
          </section>

          <section className="product-dashboard-section" aria-labelledby="trade-plan-title">
            <div className="section-header"><div><span className="section-number">03</span><h2 id="trade-plan-title">{tradeEligible ? "Trade Plan" : "No Trade"}</h2></div><span>{tradeEligible ? "Validated plan" : "Capital protection is the valid action"}</span></div>
            {tradeEligible ? <div className="trade-plan-grid">
              <span><small>Instrument</small><strong>NIFTY Options</strong></span><span><small>Direction</small><strong>{finalDecision?.trade_decision}</strong></span>
              <span><small>Entry Zone</small><strong>{finalDecision?.entry_zone ?? decision.entry_zone}</strong></span><span><small>Stop Loss</small><strong>{finalDecision?.stop_loss ?? decision.stop_loss}</strong></span>
              <span><small>Target</small><strong>{finalDecision?.target ?? decision.target}</strong></span><span><small>Invalidation</small><strong>{finalDecision?.invalidation_level ?? decision.invalidation_level}</strong></span>
              <span><small>Risk / Reward</small><strong>{Number(finalDecision?.risk_reward_ratio ?? checklistRr?.risk_reward_ratio ?? 0).toFixed(2)}</strong></span><span><small>Position Size</small><strong>{finalDecision?.position_size ?? checklistRr?.position_size ?? 0}</strong></span>
            </div> : <div className="no-trade-panel"><strong>Conditions do not support a qualified trade.</strong><p>No Trade protects capital when evidence, freshness, provider quality, or risk requirements fail.</p><ul>{noTradeReasons.slice(0, 6).map((reason) => <li key={reason}>{reason}</li>)}</ul></div>}
          </section>

          <section className="product-dashboard-section" aria-labelledby="key-levels-title">
            <div className="section-header"><div><span className="section-number">04</span><h2 id="key-levels-title">Key Levels</h2></div><span>Levels that define risk and invalidate the view</span></div>
            <div className="table-wrap"><table className="table key-levels-table"><thead><tr><th>Level</th><th>Value</th><th>Purpose</th></tr></thead><tbody>
              <tr><td>Support</td><td>{decision.support}</td><td>Nearest confirmed demand</td></tr>
              <tr><td>Resistance</td><td>{decision.resistance}</td><td>Nearest confirmed supply</td></tr>
              <tr><td>Entry Zone</td><td>{finalDecision?.entry_zone ?? decision.entry_zone}</td><td>Valid only when all gates pass</td></tr>
              <tr><td>Invalidation</td><td>{finalDecision?.invalidation_level ?? decision.invalidation_level}</td><td>Closes the current thesis</td></tr>
              <tr><td>VWAP</td><td>{decision.factor_snapshot?.vwap_relation ?? "Unavailable"}</td><td>Intraday value reference</td></tr>
            </tbody></table></div>
          </section>

          <section className="product-dashboard-section" aria-labelledby="system-trust-title">
            <div className="section-header"><div><span className="section-number">05</span><h2 id="system-trust-title">System Trust</h2></div><span>{dataQuality?.usable_for_trade ? "Data usable" : "Recommendation blocked"}</span></div>
            <div className="system-trust-grid">
              <span><small>Data Quality</small><strong>{dataQuality?.quality_score ?? 0}/100 · {dataQuality?.status ?? "UNKNOWN"}</strong></span>
              <span><small>Latest Candle</small><strong>{formatTime(market?.last_candle_timestamp)}</strong></span>
              <span><small>Feed Delay</small><strong>{market?.feed_delay_seconds ?? "-"}s</strong></span>
              <span><small>Market Session</small><strong>{marketStatusLabel}</strong></span>
              <span><small>API / Database</small><strong>{health?.api?.healthy && health?.db?.healthy ? "Ready" : "Review"}</strong></span>
              <span><small>Market Provider</small><strong>{health?.market_data?.healthy ? "Available" : "Unavailable"}</strong></span>
              <span><small>Broker Mode</small><strong>{health?.broker?.connected ? "Connected" : "Paper only"}</strong></span>
              <span><small>Risk State</small><strong>{risk?.active_risk_state ?? "UNKNOWN"}</strong></span>
              <span><small>Realtime</small><strong>{socketStatus}</strong></span>
            </div>
            {dataQuality?.critical_errors?.length > 0 && <div className="missing-data-banner" role="alert"><strong>Trade plan blocked by data quality</strong>{dataQuality.critical_errors.slice(0, 5).map((item: string) => <span key={item}>{item}</span>)}</div>}
          </section>

          <details className="dashboard-advanced-details">
            <summary>Advanced evidence and diagnostics</summary>
            <div className="confidence-evidence-panel">
              <div className="confidence-evidence-heading">
                <div><strong>Trade Confidence Factors</strong><p>{finalDecision?.trade_confidence?.meaning ?? "Decision readiness evidence and contribution trace."}</p></div>
                <span>{confidence}/100 · {finalDecision?.trade_confidence?.label ?? "UNAVAILABLE"}</span>
              </div>
              <div className="table-wrap confidence-evidence-table-wrap">
                <table className="table confidence-evidence-table">
                  <thead><tr><th>Factor</th><th>State</th><th>Contribution</th><th>Weight</th><th>Source</th><th>Observed</th></tr></thead>
                  <tbody>
                    {(finalDecision?.trade_confidence?.factors ?? []).map((factor) => (
                      <tr key={factor.name}>
                        <td>{String(factor.name ?? "unknown").replace(/_/g, " ")}</td>
                        <td><span className={`status-pill status-pill-${factor.available ? badgeTone(factor.contribution ? "PASS" : "WARN") : "danger"}`}>{factor.available ? (factor.contribution ? "Supporting" : "Not passed") : "Unavailable"}</span></td>
                        <td>{factor.contribution ?? 0} pts</td>
                        <td>{factor.weight ?? 0} pts</td>
                        <td>{factor.source ?? "Unavailable"}</td>
                        <td>{formatTime(factor.timestamp)}</td>
                      </tr>
                    ))}
                    {!finalDecision?.trade_confidence?.factors?.length && <tr><td colSpan={6}>Factor trace is unavailable for this decision.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="checklist-panel">{checklistRows.map((row) => <div className="checklist-row" key={row.label}><span className={`status-pill status-pill-${badgeTone(row.status)}`}>{row.status}</span><strong>{row.label}</strong><p>{row.reason}</p><small>{row.weight} pts</small></div>)}</div>
          </details>
        </>
      )}
    </section>
  );
}
