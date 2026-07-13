import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { canAccessRoute, getCurrentRole, hasAuthToken, type Role } from "../roles";

type SidebarProps = { collapsed: boolean; onNavigate: () => void };
type NavItem = { to: string; label: string; icon: string; mobile?: boolean };

const primaryItems: NavItem[] = [
  { to: "/", label: "Dashboard", icon: "grid", mobile: true },
  { to: "/market", label: "Market", icon: "pulse", mobile: true },
  { to: "/strategies", label: "Strategies", icon: "history" },
  { to: "/trade", label: "Orders", icon: "trade", mobile: true },
  { to: "/paper-trades", label: "Positions", icon: "grid", mobile: true },
  { to: "/trade-journal", label: "History", icon: "history" },
  { to: "/settings", label: "Risk", icon: "settings" },
  { to: "/subscription", label: "Settings", icon: "settings" },
];
const advancedItems: NavItem[] = [
  { to: "/signals", label: "Live Analysis", icon: "pulse" },
  { to: "/candles", label: "Candles", icon: "pulse" },
  { to: "/copilot", label: "Market Copilot", icon: "spark" },
  { to: "/execution", label: "Execution", icon: "pulse" },
  { to: "/history", label: "Backtest Results", icon: "history" },
  { to: "/jobs", label: "Jobs", icon: "history" },
  { to: "/institutional", label: "Institutional", icon: "grid" },
  { to: "/investing", label: "Investing", icon: "trade" },
  { to: "/trading-engine", label: "Trading Engine", icon: "settings" },
  { to: "/security", label: "Security", icon: "settings" },
];
const adminItems: NavItem[] = [
  { to: "/admin/users", label: "Users", icon: "grid" },
  { to: "/operations", label: "System status", icon: "pulse" },
  { to: "/dhan-login", label: "Broker setup", icon: "trade" },
];

export default function Sidebar({ collapsed, onNavigate }: SidebarProps) {
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

  const allowedPrimary = primaryItems.filter((item) => canAccessRoute(role, item.to));
  const allowedAdvanced = advancedItems.filter((item) => canAccessRoute(role, item.to));
  const allowedAdmin = adminItems.filter((item) => canAccessRoute(role, item.to));
  const navigate = () => { setMobileMoreOpen(false); onNavigate(); };
  const renderLink = (item: NavItem, mobilePanel = false) => (
    <NavLink key={`${mobilePanel ? "mobile" : "desktop"}-${item.to}`} to={item.to} end={item.to === "/"} onClick={navigate} data-mobile={item.mobile ? "true" : "false"} className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
      <span className={`nav-icon nav-icon-${item.icon}`} aria-hidden="true" /><span>{item.label}</span>
    </NavLink>
  );

  return <aside className={`sidebar qg-sidebar${collapsed ? " is-collapsed" : ""}`} aria-label="Application navigation">
    <nav className="sidebar-nav" aria-label="Primary navigation">
      {allowedPrimary.map((item) => renderLink(item))}
      {allowedAdvanced.length > 0 && <div className="qg-admin-nav qg-advanced-nav"><button type="button" className="qg-admin-toggle" aria-expanded={advancedOpen} onClick={() => setAdvancedOpen((value) => !value)}><span>Advanced</span><span aria-hidden="true">{advancedOpen ? "−" : "+"}</span></button>{advancedOpen && <div>{allowedAdvanced.map((item) => renderLink(item))}</div>}</div>}
      {allowedAdmin.length > 0 && <div className="qg-admin-nav"><button type="button" className="qg-admin-toggle" aria-expanded={adminOpen} onClick={() => setAdminOpen((value) => !value)}><span>Admin</span><span aria-hidden="true">{adminOpen ? "−" : "+"}</span></button>{adminOpen && <div>{allowedAdmin.map((item) => renderLink(item))}</div>}</div>}
      <button type="button" className="qg-mobile-more" aria-expanded={mobileMoreOpen} aria-controls="qg-mobile-navigation" onClick={() => setMobileMoreOpen((value) => !value)}><span className="nav-icon nav-icon-settings" aria-hidden="true" /><span>More</span></button>
    </nav>
    {mobileMoreOpen && <div className="qg-mobile-nav-panel" id="qg-mobile-navigation"><div className="qg-mobile-nav-header"><strong>Navigation</strong><button type="button" onClick={() => setMobileMoreOpen(false)} aria-label="Close navigation">×</button></div><nav aria-label="More navigation">{allowedPrimary.filter((item) => !item.mobile).map((item) => renderLink(item, true))}{allowedAdvanced.map((item) => renderLink(item, true))}{allowedAdmin.map((item) => renderLink(item, true))}</nav></div>}
  </aside>;
}
