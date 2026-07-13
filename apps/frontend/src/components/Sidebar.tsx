import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { canAccessRoute, getCurrentRole, hasAuthToken, type Role } from "../roles";

type SidebarProps = { collapsed: boolean; onNavigate: () => void };
type NavItem = { to: string; label: string; icon: string; mobile?: boolean };

const primaryItems: NavItem[] = [
  { to: "/", label: "Market Decision", icon: "grid", mobile: true },
  { to: "/signals", label: "Live Analysis", icon: "pulse", mobile: true },
  { to: "/strategies", label: "Strategies", icon: "history", mobile: true },
  { to: "/trade", label: "Orders", icon: "trade", mobile: true },
  { to: "/paper-trades", label: "Positions", icon: "grid", mobile: true },
  { to: "/trade-journal", label: "Trade History", icon: "history" },
  { to: "/settings", label: "Risk", icon: "settings" },
  { to: "/subscription", label: "Settings", icon: "settings" },
];
const advancedItems: NavItem[] = [
  { to: "/candles", label: "Candles", icon: "pulse" },
  { to: "/market", label: "Options Market", icon: "grid" },
  { to: "/copilot", label: "Market Copilot", icon: "spark" },
  { to: "/execution", label: "Execution", icon: "pulse" },
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
  useEffect(() => {
    const sync = () => { setRole(getCurrentRole()); setAuthenticated(hasAuthToken()); };
    window.addEventListener("quantgrid-role-change", sync); window.addEventListener("storage", sync);
    return () => { window.removeEventListener("quantgrid-role-change", sync); window.removeEventListener("storage", sync); };
  }, []);
  if (!authenticated) return null;
  const renderLink = (item: NavItem) => <NavLink key={item.to} to={item.to} end={item.to === "/"} onClick={onNavigate} data-mobile={item.mobile ? "true" : "false"} className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}><span className={`nav-icon nav-icon-${item.icon}`} aria-hidden="true" /><span>{item.label}</span></NavLink>;
  const allowedAdvanced = advancedItems.filter((item) => canAccessRoute(role, item.to));
  const allowedAdmin = adminItems.filter((item) => canAccessRoute(role, item.to));
  return <aside className={`sidebar qg-sidebar${collapsed ? " is-collapsed" : ""}`} aria-label="Application navigation"><nav className="sidebar-nav" aria-label="Primary navigation">{primaryItems.filter((item) => canAccessRoute(role, item.to)).map(renderLink)}{allowedAdvanced.length > 0 && <div className="qg-admin-nav qg-advanced-nav"><button type="button" className="qg-admin-toggle" aria-expanded={advancedOpen} onClick={() => setAdvancedOpen((value) => !value)}><span>Advanced</span><span aria-hidden="true">{advancedOpen ? "−" : "+"}</span></button>{advancedOpen && <div>{allowedAdvanced.map(renderLink)}</div>}</div>}{allowedAdmin.length > 0 && <div className="qg-admin-nav"><button type="button" className="qg-admin-toggle" aria-expanded={adminOpen} onClick={() => setAdminOpen((value) => !value)}><span>Admin</span><span aria-hidden="true">{adminOpen ? "−" : "+"}</span></button>{adminOpen && <div>{allowedAdmin.map(renderLink)}</div>}</div>}</nav></aside>;
}
