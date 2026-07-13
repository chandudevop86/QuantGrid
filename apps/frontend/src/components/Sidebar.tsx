import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { canAccessRoute, getCurrentRole, hasAuthToken, type Role } from "../roles";
import { useSubscription } from "../context/SubscriptionContext";

type SidebarProps = { collapsed: boolean; onNavigate: () => void };
type NavItem = { to: string; label: string; icon: string; mobile?: boolean; entitlement?: string };

const primaryItems: NavItem[] = [
  { to: "/", label: "Dashboard", icon: "grid", mobile: true, entitlement: "dashboard.basic" },
  { to: "/market", label: "Market", icon: "pulse", mobile: true, entitlement: "options.basic" },
  { to: "/strategies", label: "Strategies", icon: "history", entitlement: "strategy.performance" },
  { to: "/trade", label: "Orders", icon: "trade", mobile: true, entitlement: "paper_trade.manual" },
  { to: "/paper-trades", label: "Positions", icon: "grid", mobile: true, entitlement: "paper_trade.manual" },
  { to: "/trade-journal", label: "History", icon: "history", entitlement: "export.csv" },
  { to: "/settings", label: "Risk", icon: "settings", entitlement: "risk.advanced" },
  { to: "/subscription", label: "Settings", icon: "settings" },
];
const advancedItems: NavItem[] = [
  { to: "/signals", label: "Live Analysis", icon: "pulse", entitlement: "signals.recent_25" },
  { to: "/candles", label: "Candles", icon: "pulse", entitlement: "chart.advanced" },
  { to: "/copilot", label: "Market Copilot", icon: "spark", entitlement: "dashboard.advanced" },
  { to: "/execution", label: "Execution", icon: "pulse", entitlement: "paper_trade.automated" },
  { to: "/history", label: "Backtest Results", icon: "history", entitlement: "backtest.basic" },
  { to: "/jobs", label: "Jobs", icon: "history" },
  { to: "/institutional", label: "Institutional", icon: "grid", entitlement: "institutional.flow" },
  { to: "/investing", label: "Investing", icon: "trade" },
  { to: "/trading-engine", label: "Trading Engine", icon: "settings", entitlement: "paper_trade.automated" },
  { to: "/security", label: "Security", icon: "settings" },
];
const adminItems: NavItem[] = [
  { to: "/admin/users", label: "Users", icon: "grid", entitlement: "admin.users" },
  { to: "/operations", label: "System status", icon: "pulse", entitlement: "admin.system" },
  { to: "/dhan-login", label: "Broker setup", icon: "trade", entitlement: "admin.broker" },
];

export default function Sidebar({ collapsed, onNavigate }: SidebarProps) {
  const { canAccess, isLoading } = useSubscription();
  const [role, setRole] = useState<Role>(getCurrentRole());
  const [authenticated, setAuthenticated] = useState(hasAuthToken());
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [adminOpen, setAdminOpen] = useState(false);
  const [mobileMoreOpen, setMobileMoreOpen] = useState(false);

  useEffect(() => {
    const sync = () => { setRole(getCurrentRole()); setAuthenticated(hasAuthToken()); };
    window.addEventListener("quantgrid-role-change", sync);
    window.addEventListener("storage", sync);
    return () => { window.removeEventListener("quantgrid-role-change", sync); window.removeEventListener("storage", sync); };
  }, []);
  if (!authenticated) return null;

  const allowed = (item: NavItem) => canAccessRoute(role, item.to) && (!item.entitlement || canAccess(item.entitlement));
  const allowedPrimary = primaryItems.filter(allowed);
  const allowedAdvanced = advancedItems.filter(allowed);
  const allowedAdmin = adminItems.filter(allowed);
  const navigate = () => { setMobileMoreOpen(false); onNavigate(); };
  const renderLink = (item: NavItem, mobilePanel = false) => (
    <NavLink key={`${mobilePanel ? "mobile" : "desktop"}-${item.to}`} to={item.to} end={item.to === "/"} onClick={navigate} data-mobile={item.mobile ? "true" : "false"} className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
      <span className={`nav-icon nav-icon-${item.icon}`} aria-hidden="true" /><span>{item.label}</span>
    </NavLink>
  );

  return <aside className={`sidebar qg-sidebar${collapsed ? " is-collapsed" : ""}`} aria-label="Application navigation" aria-busy={isLoading}>
    <nav className="sidebar-nav" aria-label="Primary navigation">
      {allowedPrimary.map((item) => renderLink(item))}
      {allowedAdvanced.length > 0 && <div className="qg-admin-nav qg-advanced-nav"><button type="button" className="qg-admin-toggle" aria-expanded={advancedOpen} onClick={() => setAdvancedOpen((value) => !value)}><span>Advanced</span><span aria-hidden="true">{advancedOpen ? "−" : "+"}</span></button>{advancedOpen && <div>{allowedAdvanced.map((item) => renderLink(item))}</div>}</div>}
      {allowedAdmin.length > 0 && <div className="qg-admin-nav"><button type="button" className="qg-admin-toggle" aria-expanded={adminOpen} onClick={() => setAdminOpen((value) => !value)}><span>Admin</span><span aria-hidden="true">{adminOpen ? "−" : "+"}</span></button>{adminOpen && <div>{allowedAdmin.map((item) => renderLink(item))}</div>}</div>}
      <button type="button" className="qg-mobile-more" aria-expanded={mobileMoreOpen} aria-controls="qg-mobile-navigation" onClick={() => setMobileMoreOpen((value) => !value)}><span className="nav-icon nav-icon-settings" aria-hidden="true" /><span>More</span></button>
    </nav>
    {mobileMoreOpen && <div className="qg-mobile-nav-panel" id="qg-mobile-navigation"><div className="qg-mobile-nav-header"><strong>Navigation</strong><button type="button" onClick={() => setMobileMoreOpen(false)} aria-label="Close navigation">×</button></div><nav aria-label="More navigation">{allowedPrimary.filter((item) => !item.mobile).map((item) => renderLink(item, true))}{allowedAdvanced.map((item) => renderLink(item, true))}{allowedAdmin.map((item) => renderLink(item, true))}</nav></div>}
  </aside>;
}
