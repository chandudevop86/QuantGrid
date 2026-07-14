import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

const templates = [
  { id: "breakout", name: "Breakout", description: "Momentum continuation after range expansion.", tags: ["Trend", "Volume"] },
  { id: "mean_reversion", name: "Mean Reversion", description: "Controlled pullback entries around statistical extremes.", tags: ["Range", "VWAP"] },
  { id: "supply_demand", name: "Supply & Demand", description: "Reaction-zone setups with structure-led invalidation.", tags: ["Structure", "Zones"] },
  { id: "amd", name: "AMD", description: "Accumulation, manipulation, distribution session model.", tags: ["Session", "Liquidity"] },
];

function pretty(value: string) { return value.split("_").map((part) => part[0].toUpperCase() + part.slice(1)).join(" "); }

export default function StrategyBuilder() {
  const [template, setTemplate] = useState("breakout"), [name, setName] = useState("NIFTY Opening Range"), [timeframe, setTimeframe] = useState("5m"), [risk, setRisk] = useState("1"), [minimumScore, setMinimumScore] = useState("70"), [confirmation, setConfirmation] = useState({ trend: true, volume: true, vwap: false });
  const selected = templates.find((item) => item.id === template) ?? templates[0];
  const confirmations = useMemo(() => Object.entries(confirmation).filter(([, enabled]) => enabled).map(([key]) => pretty(key)), [confirmation]);
  return <section className="dashboard-page strategy-builder-page">
    <header className="page-heading dashboard-heading"><div><span className="page-eyebrow">Research workspace</span><h1>Strategy Builder</h1><p>Compose a rule set, validate assumptions in replay, then promote it to a paper-trading workflow.</p></div><span className="strategy-draft-badge">Research draft</span></header>
    <div className="strategy-builder-grid"><section className="dashboard-section builder-template-panel"><div className="section-header"><div><span className="page-eyebrow">1 · Start point</span><h2>Strategy template</h2></div><span>{templates.length} available</span></div><div className="builder-template-list">{templates.map((item) => <button type="button" key={item.id} className={item.id === template ? "active" : ""} onClick={() => setTemplate(item.id)}><strong>{item.name}</strong><small>{item.description}</small><span>{item.tags.map((tag) => <i key={tag}>{tag}</i>)}</span></button>)}</div></section>
      <section className="dashboard-section builder-rules-panel"><div className="section-header"><div><span className="page-eyebrow">2 · Rules</span><h2>Execution constraints</h2></div><span>NIFTY · paper first</span></div><div className="builder-form"><label>Strategy name<input value={name} onChange={(event) => setName(event.target.value)} /></label><label>Timeframe<select value={timeframe} onChange={(event) => setTimeframe(event.target.value)}>{["1m", "3m", "5m", "15m", "1h"].map((value) => <option key={value}>{value}</option>)}</select></label><label>Risk per trade (%)<input type="number" min="0.1" max="5" step="0.1" value={risk} onChange={(event) => setRisk(event.target.value)} /></label><label>Minimum quality score<input type="number" min="0" max="100" value={minimumScore} onChange={(event) => setMinimumScore(event.target.value)} /></label></div><fieldset className="builder-confirmations"><legend>Required confirmations</legend>{Object.entries(confirmation).map(([key, enabled]) => <label key={key}><input type="checkbox" checked={enabled} onChange={(event) => setConfirmation((current) => ({ ...current, [key]: event.target.checked }))} />{pretty(key)}</label>)}</fieldset></section>
      <aside className="builder-preview"><span className="page-eyebrow">3 · Review</span><h2>{name || "Untitled strategy"}</h2><p>{selected.description}</p><dl><div><dt>Template</dt><dd>{selected.name}</dd></div><div><dt>Chart interval</dt><dd>{timeframe}</dd></div><div><dt>Risk budget</dt><dd>{risk}% per trade</dd></div><div><dt>Quality gate</dt><dd>{minimumScore}/100</dd></div><div><dt>Confirmations</dt><dd>{confirmations.length ? confirmations.join(" · ") : "None selected"}</dd></div></dl><div className="builder-preview-actions"><Link to="/history">Run backtest <span>↗</span></Link><Link to="/trading-engine">Open paper engine <span>↗</span></Link></div><small>Draft settings are local to this browser until strategy persistence is enabled by the backend.</small></aside></div>
  </section>;
}
