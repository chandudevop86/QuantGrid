export type DecisionReason = { text: string; status: "pass" | "warning" | "fail" };

export default function DecisionReasons({ reasons }: { reasons: DecisionReason[] }) {
  return (
    <article className="qg-card">
      <div className="qg-section-heading"><div><span>Decision context</span><h2>Why this decision</h2></div></div>
      <ul className="qg-reason-list">
        {reasons.slice(0, 4).map((reason, index) => (
          <li key={`${reason.text}-${index}`}>
            <span className={`qg-state-icon qg-state-${reason.status}`} aria-label={reason.status}>{reason.status === "pass" ? "✓" : reason.status === "fail" ? "×" : "!"}</span>
            <span>{reason.text}</span>
          </li>
        ))}
      </ul>
    </article>
  );
}
