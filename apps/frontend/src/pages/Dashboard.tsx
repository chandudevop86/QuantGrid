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
  const { operations, loading, error, refresh } = useOperationsStatus();
  if (!hasAuthToken()) return <section className="qg-guest-landing"><span>Risk-first NIFTY options</span><h1>Trade with discipline, not impulse.</h1><p>Sign in to see one clear market decision, the reasons behind it, and the price levels that matter.</p><aside><strong>Decision support, not a profit promise.</strong><p>QuantGrid supports structured analysis and risk management. Validate decisions and use paper mode before live execution.</p></aside></section>;
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

  return <section className="qg-market-dashboard" aria-label="Market decision dashboard">
    <div className="qg-dashboard-primary"><DecisionCard decision={normalizeDecision(recommendation)} confidence={confidence} regime={text(regime)} risk={text(risk)} reason={text(explanation)} updatedAt={operations.updated_at} /><DecisionReasons reasons={reasons} /></div>
    <div className="qg-dashboard-secondary"><KeyLevelsCard levels={levels} /><TradingChecklist items={checklistItems} /></div>
    <MarketChart support={number(support)} resistance={number(resistance)} />
    <RecentSignals />
  </section>;
}
