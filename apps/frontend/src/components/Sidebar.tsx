import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { useUiMode } from "../hooks/useUiMode";
import { canAccessRoute, getCurrentRole, hasAuthToken } from "../roles";

export default function Sidebar() {
  const [role, setRole] = useState(getCurrentRole());
  const [authenticated, setAuthenticated] = useState(hasAuthToken());
  const uiMode = useUiMode();
  const navItems = [
    { to: "/", label: "Overview", icon: "grid" },
    { to: "/market", label: "Market", icon: "pulse" },
    { to: "/signals", label: "Signals", icon: "spark" },
    { to: "/paper-trades", label: "Paper Trades", icon: "trade" },
    { to: "/history", label: "History", icon: "history" },
    { to: "/settings", label: "Risk & Settings", icon: "settings" },
  ];
  const advancedItems = [
    { to: "/analysis", label: "Live Analysis", icon: "spark" },
    { to: "/trade", label: "Order Ticket", icon: "trade" },
    { to: "/execution", label: "Execution", icon: "pulse" },
    { to: "/strategies", label: "Strategies", icon: "history" },
    { to: "/operations", label: "Operations", icon: "grid" },
    { to: "/security", label: "Security", icon: "settings" },
  ];
  const adminItems = [
    { to: "/dhan-login", label: "Broker Login", icon: "trade" },
    { to: "/admin/users", label: "Users", icon: "settings" },
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

        {authenticated && uiMode === "developer" && (role === "admin" || role === "developer") && (
          <>
            <span className="sidebar-label sidebar-section-label">Advanced</span>
            {advancedItems.filter((item) => canAccessRoute(role, item.to)).map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => `nav-link nav-link-advanced${isActive ? " active" : ""}`}
              >
                <span className={`nav-icon nav-icon-${item.icon}`} aria-hidden="true" />
                <span>{item.label}</span>
              </NavLink>
            ))}
          </>
        )}

        {authenticated && uiMode === "developer" && role === "admin" && (
          <>
            <span className="sidebar-label sidebar-section-label">Administration</span>
            {adminItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) => `nav-link nav-link-advanced${isActive ? " active" : ""}`}
              >
                <span className={`nav-icon nav-icon-${item.icon}`} aria-hidden="true" />
                <span>{item.label}</span>
              </NavLink>
            ))}
          </>
        )}
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
