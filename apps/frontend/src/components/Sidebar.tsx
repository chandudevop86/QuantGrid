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
const adminItems: NavItem[] = [
  { to: "/admin/users", label: "Users", icon: "grid" },
  { to: "/operations", label: "System status", icon: "pulse" },
  { to: "/dhan-login", label: "Broker setup", icon: "trade" },
];

export default function Sidebar({ collapsed, onNavigate }: SidebarProps) {
  const [role, setRole] = useState<Role>(getCurrentRole());
  const [authenticated, setAuthenticated] = useState(hasAuthToken());
  const [adminOpen, setAdminOpen] = useState(false);
  useEffect(() => {
    const sync = () => { setRole(getCurrentRole()); setAuthenticated(hasAuthToken()); };
    window.addEventListener("quantgrid-role-change", sync); window.addEventListener("storage", sync);
    return () => { window.removeEventListener("quantgrid-role-change", sync); window.removeEventListener("storage", sync); };
  }, []);
  if (!authenticated) return null;
  const renderLink = (item: NavItem) => <NavLink key={item.to} to={item.to} end={item.to === "/"} onClick={onNavigate} data-mobile={item.mobile ? "true" : "false"} className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}><span className={`nav-icon nav-icon-${item.icon}`} aria-hidden="true" /><span>{item.label}</span></NavLink>;
  const allowedAdmin = adminItems.filter((item) => canAccessRoute(role, item.to));
  return <aside className={`sidebar qg-sidebar${collapsed ? " is-collapsed" : ""}`} aria-label="Application navigation"><nav className="sidebar-nav" aria-label="Primary navigation">{primaryItems.filter((item) => canAccessRoute(role, item.to)).map(renderLink)}{allowedAdmin.length > 0 && <div className="qg-admin-nav"><button type="button" className="qg-admin-toggle" aria-expanded={adminOpen} onClick={() => setAdminOpen((value) => !value)}><span>Admin</span><span aria-hidden="true">{adminOpen ? "−" : "+"}</span></button>{adminOpen && <div>{allowedAdmin.map(renderLink)}</div>}</div>}</nav></aside>;
}
