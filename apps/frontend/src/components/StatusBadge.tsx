type StatusTone = "positive" | "warning" | "danger" | "neutral";

type StatusBadgeProps = {
  children: React.ReactNode;
  tone?: StatusTone;
  className?: string;
};

export default function StatusBadge({ children, tone = "neutral", className = "" }: StatusBadgeProps) {
  return <span className={`qg-status-badge qg-status-${tone} ${className}`.trim()}>{children}</span>;
}
