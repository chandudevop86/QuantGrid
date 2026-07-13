import { useState } from "react";
import AppHeader from "../components/AppHeader";
import Sidebar from "../components/Sidebar";
import { OperationsStatusProvider } from "../context/OperationsStatusContext";
import { MarketSelectionProvider } from "../context/MarketSelectionContext";
import { SubscriptionProvider } from "../context/SubscriptionContext";

type AppLayoutProps = { children: React.ReactNode };

export default function AppLayout({ children }: AppLayoutProps) {
  const [navigationCollapsed, setNavigationCollapsed] = useState(false);
  return <MarketSelectionProvider><SubscriptionProvider><OperationsStatusProvider><div className="app-shell"><Sidebar collapsed={navigationCollapsed} onNavigate={() => setNavigationCollapsed(false)} /><main className="app-main"><AppHeader onMenuToggle={() => setNavigationCollapsed((value) => !value)} /><div className="app-content">{children}</div></main></div></OperationsStatusProvider></SubscriptionProvider></MarketSelectionProvider>;
}
