import { useEffect, useState } from "react";
import { getCurrentMode, modeLabels, modes, setCurrentMode, type TradingMode } from "../mode";
import { getCurrentRole, roleLabels, roles, setCurrentRole, type Role } from "../roles";

export default function Topbar() {
  const [role, setRole] = useState<Role>(getCurrentRole());
  const [mode, setMode] = useState<TradingMode>(getCurrentMode());

  useEffect(() => {
    const syncRole = () => setRole(getCurrentRole());
    const syncMode = () => setMode(getCurrentMode());
    window.addEventListener("quantgrid-role-change", syncRole);
    window.addEventListener("quantgrid-mode-change", syncMode);
    window.addEventListener("storage", syncRole);
    window.addEventListener("storage", syncMode);
    return () => {
      window.removeEventListener("quantgrid-role-change", syncRole);
      window.removeEventListener("quantgrid-mode-change", syncMode);
      window.removeEventListener("storage", syncRole);
      window.removeEventListener("storage", syncMode);
    };
  }, []);

  const changeRole = (nextRole: Role) => {
    setCurrentRole(nextRole);
    setRole(nextRole);
    window.location.assign("/");
  };

  const changeMode = (nextMode: TradingMode) => {
    setCurrentMode(nextMode);
    setMode(nextMode);
  };

  return (
    <header className="topbar">
      <div>
        <strong>Trading Dashboard</strong>
        <span>Service health and execution overview</span>
      </div>
      <div className="topbar-actions">
        <select
          className="role-select"
          value={role}
          onChange={(event) => changeRole(event.target.value as Role)}
          aria-label="Current role"
        >
          {roles.map((item) => (
            <option key={item} value={item}>
              {roleLabels[item]}
            </option>
          ))}
        </select>
        <div className="mode-toggle" aria-label="Trading mode">
          {modes.map((item) => (
            <button
              key={item}
              type="button"
              className={mode === item ? "active" : ""}
              onClick={() => changeMode(item)}
            >
              {modeLabels[item]}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}
