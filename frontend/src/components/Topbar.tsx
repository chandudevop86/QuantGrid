import { useEffect, useState } from "react";
import { getCurrentRole, roleLabels, roles, setCurrentRole, type Role } from "../roles";

export default function Topbar() {
  const [role, setRole] = useState<Role>(getCurrentRole());

  useEffect(() => {
    const syncRole = () => setRole(getCurrentRole());
    window.addEventListener("quantgrid-role-change", syncRole);
    window.addEventListener("storage", syncRole);
    return () => {
      window.removeEventListener("quantgrid-role-change", syncRole);
      window.removeEventListener("storage", syncRole);
    };
  }, []);

  const changeRole = (nextRole: Role) => {
    setCurrentRole(nextRole);
    setRole(nextRole);
    window.location.assign("/");
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
        <span className="environment-badge">Paper Mode</span>
      </div>
    </header>
  );
}
