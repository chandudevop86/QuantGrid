import { useEffect, useState } from "react";
import { api } from "../api";
import { getCurrentMode, modeLabels, modes, setCurrentMode, type TradingMode } from "../mode";
import {
  clearCurrentAuth,
  getCurrentRole,
  hasAuthToken,
  roleLabels,
  setCurrentAuth,
  type Role,
} from "../roles";

export default function Topbar() {
  const [role, setRole] = useState<Role>(getCurrentRole());
  const [mode, setMode] = useState<TradingMode>(getCurrentMode());
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(hasAuthToken());

  useEffect(() => {
    const syncRole = () => {
      setRole(getCurrentRole());
      setIsAuthenticated(hasAuthToken());
    };
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

  const login = async (event: React.FormEvent) => {
    event.preventDefault();
    setAuthError(null);

    try {
      const response = await api.login({ username, password });
      setCurrentAuth(response.role, response.access_token);
      setRole(response.role);
      setIsAuthenticated(true);
      setPassword("");
      window.location.assign("/");
    } catch (error: any) {
      setAuthError(error?.response?.data?.detail ?? "Login failed");
    }
  };

  const logout = () => {
    clearCurrentAuth();
    setRole("viewer");
    setIsAuthenticated(false);
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
        {isAuthenticated ? (
          <div className="auth-status">
            <span>{roleLabels[role]}</span>
            <button type="button" onClick={logout}>
              Logout
            </button>
          </div>
        ) : (
          <form className="auth-form" onSubmit={login}>
            <input
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="Username"
              aria-label="Username"
            />
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Password"
              type="password"
              aria-label="Password"
            />
            <button type="submit">Login</button>
            {authError && <span className="auth-error">{authError}</span>}
          </form>
        )}
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
