import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import AppHeader from "../components/AppHeader";
import Sidebar from "../components/Sidebar";
import WorkspaceCommandPalette from "../components/WorkspaceCommandPalette";
import { OperationsStatusProvider, useOperationsStatus } from "../context/OperationsStatusContext";
import { MarketSelectionProvider, useMarketSelection } from "../context/MarketSelectionContext";
import { SubscriptionProvider } from "../context/SubscriptionContext";
import { canAccessRoute, getCurrentRole, hasAuthToken } from "../roles";

type AppLayoutProps = { children: React.ReactNode };

export default function AppLayout({ children }: AppLayoutProps) {
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const location = useLocation();
  const isTerminal = location.pathname === "/trade";

  useEffect(() => {
    setNavigationOpen(false);
    setSearchOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        if (!hasAuthToken()) return;
        event.preventDefault();
        setSearchOpen((value) => !value);
      }
      if (event.key === "Escape") {
        setSearchOpen(false);
        setNavigationOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <MarketSelectionProvider>
      <SubscriptionProvider>
        <OperationsStatusProvider>
          <div className={`app-shell qg-workspace-v3${isTerminal ? " app-shell-terminal" : ""}`}>
            <Sidebar collapsed={!navigationOpen} onNavigate={() => setNavigationOpen(false)} />
            {navigationOpen && (
              <button
                type="button"
                className="qg-navigation-backdrop"
                aria-label="Close navigation"
                onClick={() => setNavigationOpen(false)}
              />
            )}
            <main className="app-main" id="main-content">
              <AppHeader
                onMenuToggle={() => setNavigationOpen((value) => !value)}
                onSearch={() => setSearchOpen(true)}
              />
              <div className="app-content">{children}</div>
            </main>
            {!isTerminal && <WorkspaceContext />}
            {searchOpen && <WorkspaceCommandPalette onClose={() => setSearchOpen(false)} />}
          </div>
        </OperationsStatusProvider>
      </SubscriptionProvider>
    </MarketSelectionProvider>
  );
}

function formattedCandle(value: unknown): string {
  if (typeof value !== "string" || !value) return "Not reported";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Invalid source timestamp";
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
  }).format(date) + " IST";
}

function WorkspaceContext() {
  const { label } = useMarketSelection();
  const { operations, loading, error, socketStatus } = useOperationsStatus();
  const market = operations?.market_status;
  const session = typeof market?.session_state === "string" ? market.session_state : null;
  const candle = market?.last_candle_timestamp;
  const links = [
    { to: "/market", label: "Options & market", detail: "Verify chain and price data" },
    { to: "/institutional", label: "Institutional flows", detail: "Check dated source reports" },
    { to: "/investing", label: "Investment research", detail: "Quality / growth watchlist" },
    { to: "/settings", label: "Risk controls", detail: "Review execution guardrails" },
  ].filter((item) => hasAuthToken() && canAccessRoute(getCurrentRole(), item.to));

  return (
    <aside className="qg-workspace-context" aria-label="Research context">
      <header>
        <div>
          <span className="qg-context-kicker">Market workspace</span>
          <strong>Data & system</strong>
        </div>
        <span className={`qg-context-state${error ? " is-unavailable" : ""}`}>
          {error ? "Unavailable" : loading ? "Checking" : "Monitor"}
        </span>
      </header>
      <div className="qg-context-body">
        <div className="qg-context-instrument">
          <span className="qg-context-kicker">Selected instrument</span>
          <strong>{label}</strong>
          <small>Selection only · no quote implied</small>
        </div>
        <div className="qg-context-data">
          <div><span>Market session</span><strong>{error ? "Unknown" : session ?? "Not reported"}</strong></div>
          <div><span>Updates channel</span><strong>{socketStatus === "online" ? "Connected" : socketStatus === "polling" ? "Polling" : "Offline"}</strong></div>
          <div><span>Last candle</span><strong>{error ? "Unavailable" : formattedCandle(candle)}</strong></div>
        </div>
        {(error || !candle) && <p className="qg-context-caution" role="status">
          {error || "No verified current market quote is available in this panel."}
        </p>}
        <div className="qg-context-links">
          <span className="qg-context-kicker">Go to workspace</span>
          {links.map((item) => (
            <Link to={item.to} key={item.to}>
              <span><strong>{item.label}</strong><small>{item.detail}</small></span>
              <span aria-hidden="true">↗</span>
            </Link>
          ))}
        </div>
      </div>
      <footer className="qg-context-footer">
        <strong>Research first</strong>
        <span>Display timestamps do not establish exchange quote freshness. Broker and order status must be verified separately.</span>
      </footer>
    </aside>
  );
}
