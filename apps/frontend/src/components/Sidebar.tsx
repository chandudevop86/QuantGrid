import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { canAccessRoute, getCurrentRole, hasAuthToken } from "../roles";

export default function Sidebar() {
  const [role, setRole] = useState(getCurrentRole());
  const [authenticated, setAuthenticated] = useState(hasAuthToken());
  const navItems = [
    { to: "/", label: "Overview", icon: "grid" },
    { to: "/candles", label: "Market", icon: "pulse" },
    { to: "/analysis", label: "Live Analysis", icon: "spark" },
    { to: "/trade", label: "Trade", icon: "trade" },
    { to: "/strategies", label: "Strategies", icon: "history" },
    { to: "/execution", label: "Execution", icon: "settings" },
  ];

  useEffect(() => {
    const syncAuth = () => {
      setRole(getCurrentRole());
      setAuthenticated(hasAuthToken());
    };

    window.addEventListener("quantgrid-role-change", syncAuth);
    window.addEventListener("storage", syncAuth);
    return () => {
      window.removeEventListener("quantgrid-role-change", syncAuth);
      window.removeEventListener("storage", syncAuth);
    };
  }, []);

  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark">QG</span>
        <div>
          <strong>QuantGrid</strong>
          <span>Trading Console</span>
        </div>
      </div>

      <nav className="sidebar-nav" aria-label="Primary navigation">
        <span className="sidebar-label">Workspace</span>
        {navItems.filter((item) => authenticated && canAccessRoute(role, item.to)).map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
          >
            <span className={`nav-icon nav-icon-${item.icon}`} aria-hidden="true" />
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-footer">
        <span className="sidebar-status-dot" aria-hidden="true" />
        <div>
          <strong>Engine online</strong>
          <span>Monitoring markets</span>
        </div>
      </div>
    </aside>
  );
}
