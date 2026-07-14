import { useState } from "react";
import AppHeader from "../components/AppHeader";
import Sidebar from "../components/Sidebar";
import { OperationsStatusProvider } from "../context/OperationsStatusContext";
import { MarketSelectionProvider } from "../context/MarketSelectionContext";
import { SubscriptionProvider } from "../context/SubscriptionContext";
import { useMarketSelection } from "../context/MarketSelectionContext";

type AppLayoutProps = { children: React.ReactNode };

export default function AppLayout({ children }: AppLayoutProps) {
  const [navigationCollapsed, setNavigationCollapsed] = useState(false);
  return <MarketSelectionProvider><SubscriptionProvider><OperationsStatusProvider><div className="app-shell"><Sidebar collapsed={navigationCollapsed} onNavigate={() => setNavigationCollapsed(false)} /><main className="app-main"><AppHeader onMenuToggle={() => setNavigationCollapsed((value) => !value)} /><div className="app-content">{children}</div></main><WorkspaceContext /></div></OperationsStatusProvider></SubscriptionProvider></MarketSelectionProvider>;
}

function WorkspaceContext() {
  const { symbol } = useMarketSelection();
  const instruments = [
    ["NIFTY 50", "24,672.35", "+0.52%", "up"],
    ["BANKNIFTY", "55,342.10", "−0.24%", "down"],
    ["SENSEX", "80,490.12", "+0.31%", "up"],
    ["INDIA VIX", "12.84", "+1.08%", "down"],
  ];
  return <aside className="qg-workspace-context" aria-label="Market context">
    <header><div><span className="qg-context-kicker">Workspace</span><strong>Market pulse</strong></div><span className="qg-context-live">Live</span></header>
    <div className="qg-context-watchlist">{instruments.map(([name, price, change, direction]) => <button type="button" key={name} className={name.replace(" ", "") === symbol ? "active" : ""}><span><b>{name}</b><small>NSE</small></span><span><b>{price}</b><small className={direction === "up" ? "is-positive" : "is-negative"}>{change}</small></span></button>)}</div>
    <section className="qg-context-insight"><span className="qg-context-kicker">Session insight</span><strong>Risk remains contained</strong><p>Market breadth is positive. Keep total intraday exposure below 58% of allocated capital.</p><div><span>Exposure</span><b>42%</b></div></section>
  </aside>;
}
