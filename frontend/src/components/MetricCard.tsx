type MetricCardProps = {
  label: string;
  value: string | number;
  helper?: string;
  tone?: "neutral" | "good" | "warn";
};

export default function MetricCard({
  label,
  value,
  helper,
  tone = "neutral",
}: MetricCardProps) {
  return (
    <div className={`metric-card metric-card-${tone}`}>
      <span className="metric-label">{label}</span>
      <strong className="metric-value">{value}</strong>
      {helper && <span className="metric-helper">{helper}</span>}
    </div>
  );
}
