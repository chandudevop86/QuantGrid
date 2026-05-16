import { NavLink } from "react-router-dom";

export default function Sidebar() {
  const navItems = [
    { to: "/", label: "Dashboard" },
    { to: "/candles", label: "Candles" },
    { to: "/live", label: "Live Analysis" },
    { to: "/jobs", label: "Jobs" },
    { to: "/strategies", label: "Strategies" },
    { to: "/execution", label: "Execution" },
    { to: "/trade", label: "Trade" },
  ];

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
        {navItems.map((item) => (
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
