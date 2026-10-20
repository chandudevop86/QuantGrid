import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSubscription } from "../context/SubscriptionContext";
import { canAccessRoute, getCurrentRole, hasAuthToken } from "../roles";

type Destination = { path: string; label: string; group: string; entitlement?: string };
type Props = { onClose: () => void };

const destinations: Destination[] = [
  { path: "/", label: "Dashboard", group: "Overview" },
  { path: "/market", label: "Option chain & market", group: "Trading", entitlement: "options.basic" },
  { path: "/trade", label: "Order terminal", group: "Trading", entitlement: "paper_trade.manual" },
  { path: "/paper-trades", label: "Positions", group: "Trading", entitlement: "paper_trade.manual" },
  { path: "/signals", label: "Live analysis", group: "Research", entitlement: "signals.recent_25" },
  { path: "/institutional", label: "Institutional dashboard", group: "Research", entitlement: "institutional.flow" },
  { path: "/investing", label: "Investment research", group: "Research" },
  { path: "/ai-scanner", label: "AI scanner", group: "Research", entitlement: "signals.recent_25" },
  { path: "/strategies", label: "Strategies", group: "Tools", entitlement: "strategy.performance" },
  { path: "/strategy-builder", label: "Strategy builder", group: "Tools", entitlement: "strategy.performance" },
  { path: "/history", label: "Backtesting", group: "Tools", entitlement: "backtest.basic" },
  { path: "/trade-journal", label: "Trading journal", group: "Tools", entitlement: "export.csv" },
  { path: "/settings", label: "Risk dashboard", group: "Safety", entitlement: "risk.advanced" },
  { path: "/security", label: "Security", group: "Safety" },
  { path: "/operations", label: "Operations", group: "Safety" },
];

export default function WorkspaceCommandPalette({ onClose }: Props) {
  const [query, setQuery] = useState("");
  const [highlighted, setHighlighted] = useState(0);
  const { canAccess } = useSubscription();
  const navigate = useNavigate();
  const results = useMemo(() => {
    if (!hasAuthToken()) return [];
    const normalized = query.trim().toLowerCase();
    return destinations
      .filter((destination) => canAccessRoute(getCurrentRole(), destination.path))
      .filter((destination) => !destination.entitlement || canAccess(destination.entitlement))
      .filter((destination) => !normalized || `${destination.label} ${destination.group} ${destination.path}`.toLowerCase().includes(normalized));
  }, [query, canAccess]);

  useEffect(() => setHighlighted(0), [query]);
  const navigateTo = (path: string) => {
    onClose();
    navigate(path);
  };

  return (
    <div className="qg-command-layer" role="presentation">
      <button type="button" className="qg-command-backdrop" onClick={onClose} aria-label="Close quick navigation" />
      <div className="qg-command-panel" role="dialog" aria-modal="true" aria-label="Quick navigation">
        <div className="qg-command-head">
          <span>QUANTGRID / QUICK NAVIGATION</span>
          <button type="button" onClick={onClose} aria-label="Close search">Esc ✕</button>
        </div>
        <input
          autoFocus
          type="search"
          aria-label="Search allowed workspace pages"
          placeholder="Search markets, research, risk, positions…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") { event.preventDefault(); setHighlighted((value) => Math.min(results.length - 1, value + 1)); }
            if (event.key === "ArrowUp") { event.preventDefault(); setHighlighted((value) => Math.max(0, value - 1)); }
            if (event.key === "Enter" && results[highlighted]) { event.preventDefault(); navigateTo(results[highlighted].path); }
          }}
        />
        <div className="qg-command-results" aria-live="polite">
          {results.length ? results.map((item, index) => (
            <button type="button" key={item.path}
              className={index === highlighted ? "is-selected" : ""}
              onMouseEnter={() => setHighlighted(index)}
              onClick={() => navigateTo(item.path)}>
              <span><strong>{item.label}</strong><small>{item.group}</small></span>
              <span aria-hidden="true">↗</span>
            </button>
          )) : <p>No accessible pages match your search.</p>}
        </div>
        <footer>Use ↑ ↓ and Enter to navigate · Esc to close · Access follows your role and subscription.</footer>
      </div>
    </div>
  );
}
