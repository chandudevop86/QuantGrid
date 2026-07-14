import DecisionCard from "../components/DecisionCard";
import DecisionReasons, { type DecisionReason } from "../components/DecisionReasons";
import EmptyState from "../components/EmptyState";
import ErrorState from "../components/ErrorState";
import KeyLevelsCard from "../components/KeyLevelsCard";
import LoadingSkeleton from "../components/LoadingSkeleton";
import MarketChart from "../components/MarketChart";
import RecentSignals from "../components/RecentSignals";
import TradingChecklist, { type ChecklistItem } from "../components/TradingChecklist";
import { useOperationsStatus } from "../context/OperationsStatusContext";
import { hasAuthToken } from "../roles";
import FeatureGate from "../components/FeatureGate";
import { useCanAccess, useFeatureLimit } from "../context/SubscriptionContext";
import { Link } from "react-router-dom";

type ItemStatus = "pass" | "warning" | "fail";

function text(value: unknown, fallback = "Not available") { return value === null || value === undefined || value === "" ? fallback : String(value); }
function number(value: unknown) { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : undefined; }
function status(passed: unknown, warning?: unknown): ItemStatus { if (warning) return "warning"; if (passed === true) return "pass"; if (passed === false) return "fail"; return "warning"; }
function normalizeDecision(value: unknown) {
  const source = text(value, "NO TRADE").toUpperCase();
  if (source.includes("BUY")) return "BUY";
  if (source.includes("SELL")) return "SELL";
  if (source.includes("WAIT")) return "WAIT";
  return "NO TRADE";
}
function reasonText(value: unknown) {
  if (typeof value === "string") return value;
  if (value && typeof value === "object") return text((value as { reason?: unknown; message?: unknown }).reason ?? (value as { message?: unknown }).message);
  return "Confirmation is not available.";
}

export default function Dashboard() {
  const canSeeFullLevels = useCanAccess("levels.full");
  const canSeeVolume = useCanAccess("volume.basic");
  const signalLimit = useFeatureLimit("signals_history_limit") ?? 5;
  const { operations, loading, error, refresh } = useOperationsStatus();
  if (!hasAuthToken()) return <section className="qg-guest-landing">
    <div className="qg-guest-hero"><div><span>Institutional workflow for Indian markets</span><h1>Trade with discipline, not impulse.</h1><p>QuantGrid brings market intelligence, option-chain context, structured risk controls, and research tools into one focused trading workspace.</p><div className="qg-guest-actions"><Link to="/signup">Create your workspace</Link><Link to="/plans">Explore plans</Link></div><small>Built for analysis, paper practice, and repeatable execution workflows.</small></div><aside className="qg-guest-preview" aria-label="QuantGrid platform preview"><div><span>MARKET INTELLIGENCE</span><b>Structured decision flow</b></div><dl><div><dt>Market context</dt><dd>Trend · VWAP · Volume</dd></div><div><dt>Derivatives</dt><dd>OI · PCR · IV · Greeks</dd></div><div><dt>Risk control</dt><dd>Position sizing · SL · R:R</dd></div></dl><footer><i /> Paper-first environment</footer></aside></div>
    <section className="qg-guest-features" aria-label="QuantGrid capabilities"><article><span>01</span><h2>Decision intelligence</h2><p>Translate price action, volume, options flow, and market structure into an explainable setup—not a black box.</p></article><article><span>02</span><h2>Professional execution</h2><p>Use a terminal built around watchlists, chart context, order tickets, exposure, and lifecycle visibility.</p></article><article><span>03</span><h2>Research & validation</h2><p>Compare strategies, inspect performance and drawdown, then move only validated ideas to paper workflows.</p></article><article><span>04</span><h2>Risk-first operations</h2><p>Track portfolio exposure, trade outcomes, broker status, and operational safeguards in one place.</p></article></section>
    <section className="qg-guest-workflow"><div><span>ONE CONNECTED WORKFLOW</span><h2>From market context to measured execution.</h2></div><ol><li><b>01</b><span>Scan</span><small>Prioritize market and AI signal context.</small></li><li><b>02</b><span>Validate</span><small>Check structure, options data, and risk.</small></li><li><b>03</b><span>Practice</span><small>Use controlled paper-trading workflows.</small></li><li><b>04</b><span>Review</span><small>Learn from positions and trade history.</small></li></ol></section>
    <aside className="qg-guest-safety"><strong>Decision support, not a profit promise.</strong><p>QuantGrid supports structured analysis and risk management. Validate decisions and use paper mode before live execution.</p></aside>
  </section>;
  if (loading) return <section className="qg-market-dashboard"><LoadingSkeleton /></section>;
  if (error) return <section className="qg-market-dashboard"><ErrorState message={error} onRetry={() => void refresh()} /></section>;
  if (!operations?.decision) return <section className="qg-market-dashboard"><EmptyState title="No market decision yet" message="The decision will appear after the analysis pipeline publishes a qualified market snapshot." /></section>;

  const decision = operations.decision;
  const snapshot = decision.factor_snapshot ?? {};
  const finalDecision = snapshot.final_decision ?? {};
  const checklist = snapshot.checklist ?? {};
  const trend = checklist.trend ?? snapshot.trend_analysis ?? {};
  const volume = checklist.volume ?? snapshot.volume_analysis ?? {};
  const supportResistance = checklist.support_resistance ?? snapshot.support_resistance ?? {};
  const riskReward = checklist.risk_reward ?? snapshot.risk_reward ?? {};
  const recommendation = finalDecision.trade_decision ?? decision.trade_recommendation;
  const confidence = Number(finalDecision.trade_confidence?.score ?? finalDecision.confidence_score ?? decision.confidence ?? 0);
  const regime = checklist.market_regime?.market_regime ?? checklist.market_regime?.regime ?? snapshot.market_regime ?? "Unknown";
  const risk = finalDecision.risk_level ?? decision.risk_level ?? "Unknown";
  const explanation = finalDecision.explainability?.plain_english ?? finalDecision.explanation?.[0] ?? decision.simple_explanation ?? decision.score_reason ?? "Waiting for a clear confirmation.";

  const rawReasons: DecisionReason[] = [
    ...(decision.supporting_factors ?? []).map((item: unknown) => ({ text: reasonText(item), status: "pass" as const })),
    ...(decision.warnings ?? finalDecision.explainability?.warnings ?? []).map((item: unknown) => ({ text: reasonText(item), status: "warning" as const })),
    ...(finalDecision.block_reasons ?? decision.opposing_factors ?? []).map((item: unknown) => ({ text: reasonText(item), status: "fail" as const })),
  ];
  const reasons = rawReasons.length ? rawReasons.slice(0, 4) : [{ text: text(explanation), status: "warning" as const }];
  const checklistItems: ChecklistItem[] = [
    { label: "Trend", text: text(trend.reason ?? trend.trend_direction), status: status(trend.trend_direction && String(trend.trend_direction).toUpperCase() !== "SIDEWAYS", trend.warning_if_sideways) },
    { label: "Volume", text: text(volume.reason), status: status(volume.supports_trade, volume.warning) },
    { label: "Momentum", text: text(checklist.price_action?.reason), status: status(checklist.price_action?.confirmed, checklist.price_action?.warning) },
    { label: "VWAP", text: text(checklist.ema?.reason ?? snapshot.ema_analysis?.reason), status: status(checklist.ema?.ema_bias && checklist.ema.ema_bias !== "Neutral", checklist.ema?.warning ?? snapshot.ema_analysis?.warning) },
    { label: "Option chain", text: text(checklist.options_flow?.reason), status: status(checklist.options_flow?.passed, checklist.options_flow?.warning) },
    { label: "Risk", text: text(riskReward.allowed ? "Risk/reward accepted" : riskReward.warnings?.[0]), status: status(riskReward.allowed, riskReward.warnings?.[0]) },
  ];
  const support = supportResistance.support ?? decision.support;
  const resistance = supportResistance.resistance ?? decision.resistance;
  const levels = [
    { label: "Resistance", value: text(resistance) },
    { label: "Support", value: text(support) },
    { label: "Entry above", value: text(finalDecision.trade_plan?.entry_zone ?? finalDecision.entry_zone ?? supportResistance.entry_zone ?? decision.entry_zone) },
    { label: "Stop loss", value: text(finalDecision.trade_plan?.stop_loss ?? finalDecision.stop_loss ?? decision.stop_loss) },
    { label: "Target", value: text(finalDecision.trade_plan?.target ?? finalDecision.target ?? decision.target) },
    { label: "Invalidation", value: text(finalDecision.trade_plan?.invalidation_level ?? finalDecision.invalidation_level ?? supportResistance.invalidation_level ?? decision.invalidation_level) },
  ];
  const actionLabel = normalizeDecision(recommendation);
  const marketState = String(regime).replace(/_/g, " ");
  const updated = operations.updated_at ? new Date(operations.updated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "Awaiting update";

  return <section className="qg-market-dashboard" aria-label="Market decision dashboard">
    <header className="sahi-command-header">
      <div className="sahi-instrument"><span className="terminal-kicker">Market command center</span><strong>NIFTY 50</strong><span>Cash · NSE</span></div>
      <div className="sahi-market-state"><span className="market-live-dot" aria-hidden="true" /><div><small>Decision engine</small><b>{actionLabel}</b></div></div>
      <div className="sahi-market-state"><div><small>Last evaluation</small><b>{updated}</b></div></div>
      <Link className="sahi-execute-link" to="/trade">Open terminal <span aria-hidden="true">↗</span></Link>
    </header>
    <section className="sahi-risk-strip" aria-label="Market snapshot">
      <span><small>Confidence</small><b>{confidence.toFixed(0)}%</b></span>
      <span><small>Market regime</small><b>{marketState}</b></span>
      <span><small>Risk level</small><b className={String(risk).toLowerCase() === "high" ? "is-risk" : ""}>{text(risk)}</b></span>
      <span><small>Trade plan</small><b>{actionLabel === "NO TRADE" ? "Stand aside" : `${actionLabel} setup`}</b></span>
    </section>
    <div className="qg-dashboard-primary"><DecisionCard decision={normalizeDecision(recommendation)} confidence={confidence} regime={text(regime)} risk={text(risk)} reason={text(explanation)} updatedAt={operations.updated_at} /><FeatureGate feature="decision.advanced_reasons"><DecisionReasons reasons={reasons} /></FeatureGate></div>
    <div className="qg-dashboard-secondary"><FeatureGate feature="volume.basic"><TradingChecklist items={checklistItems} /></FeatureGate><KeyLevelsCard levels={canSeeFullLevels ? levels : levels.slice(0, 2)} /></div>
    <MarketChart support={number(support)} resistance={number(resistance)} showAnalysis={canSeeVolume} />
    <RecentSignals limit={signalLimit} />
  </section>;
}
