import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { canAccessRoute, getCurrentRole, hasAuthToken } from "../roles";

export default function Sidebar() {
  const [role, setRole] = useState(getCurrentRole());
  const [authenticated, setAuthenticated] = useState(hasAuthToken());
  const navItems = [
    { to: "/", label: "Dashboard" },
    { to: "/candles", label: "Candles" },
    { to: "/live", label: "Live Analysis" },
    { to: "/jobs", label: "Jobs" },
    { to: "/operations", label: "Operations" },
    { to: "/signals", label: "Signals" },
    { to: "/strategies", label: "Strategies" },
    { to: "/execution", label: "Execution" },
    { to: "/trade", label: "Trade" },
    { to: "/admin/users", label: "Users" },
    { to: "/admin/notifications", label: "Notifications" },
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
        {navItems.filter((item) => item.to === "/" || (authenticated && canAccessRoute(role, item.to))).map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
