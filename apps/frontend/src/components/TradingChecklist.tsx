import type { DecisionReason } from "./DecisionReasons";

export type ChecklistItem = DecisionReason & { label: string };

export default function TradingChecklist({ items }: { items: ChecklistItem[] }) {
  return (
    <article className="qg-card">
      <div className="qg-section-heading"><div><span>Six confirmations</span><h2>Trading checklist</h2></div></div>
      <ul className="qg-checklist">
        {items.map((item) => (
          <li key={item.label}>
            <div><span className={`qg-state-icon qg-state-${item.status}`} aria-hidden="true">{item.status === "pass" ? "✓" : item.status === "fail" ? "×" : "!"}</span><strong>{item.label}</strong></div>
            <span className={`qg-check-status qg-check-${item.status}`}>{item.status}</span>
          </li>
        ))}
      </ul>
    </article>
  );
}
