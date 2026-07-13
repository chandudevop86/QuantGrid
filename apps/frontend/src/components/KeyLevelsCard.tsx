export type KeyLevel = { label: string; value: string };

export default function KeyLevelsCard({ levels }: { levels: KeyLevel[] }) {
  return (
    <article className="qg-card">
      <div className="qg-section-heading"><div><span>Price map</span><h2>Key levels</h2></div></div>
      <dl className="qg-levels-list">
        {levels.map((level) => <div key={level.label}><dt>{level.label}</dt><dd>{level.value}</dd></div>)}
      </dl>
    </article>
  );
}
