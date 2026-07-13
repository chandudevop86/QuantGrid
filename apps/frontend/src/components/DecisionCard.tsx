import StatusBadge from "./StatusBadge";

type DecisionCardProps = {
  decision: string;
  confidence: number;
  regime: string;
  risk: string;
  reason: string;
  updatedAt?: string;
};

function decisionTone(value: string) {
  const normalized = value.toLowerCase();
  if (normalized.includes("buy")) return "positive" as const;
  if (normalized.includes("sell")) return "danger" as const;
  return "warning" as const;
}

export default function DecisionCard({ decision, confidence, regime, risk, reason, updatedAt }: DecisionCardProps) {
  return (
    <article className="qg-card qg-decision-card" aria-labelledby="current-decision-title">
      <div className="qg-card-label">Current market decision</div>
      <div className="qg-decision-heading">
        <h1 id="current-decision-title">{decision}</h1>
        <StatusBadge tone={decisionTone(decision)}>{decision}</StatusBadge>
      </div>
      <dl className="qg-decision-metrics">
        <div><dt>Confidence</dt><dd>{Math.round(confidence)}%</dd></div>
        <div><dt>Market regime</dt><dd>{regime}</dd></div>
        <div><dt>Risk level</dt><dd>{risk}</dd></div>
      </dl>
      <div className="qg-decision-reason"><span>Reason</span><p>{reason}</p></div>
      <time className="qg-updated-time" dateTime={updatedAt}>Last updated {updatedAt ? new Date(updatedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "—"}</time>
    </article>
  );
}
