import { useEffect, useState } from "react";
import { api } from "../api";
import { getApiErrorMessage } from "../api/client";
import {
  getCurrentMode,
  getCurrentUiMode,
  setCurrentMode,
  setCurrentUiMode,
  type TradingMode,
  type UiMode,
} from "../mode";
import {
  clearCurrentAuth,
  getCurrentRole,
  hasAuthToken,
  roleLabels,
  roles,
  setCurrentAuth,
  type Role,
} from "../roles";
import { getMarketStatusClass, getMarketStatusLabel, type MarketStatusLabel } from "../utils/marketStatus";

export default function Topbar() {
  const [role, setRole] = useState<Role>(getCurrentRole());
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(hasAuthToken());
  const [marketStatus, setMarketStatus] = useState<MarketStatusLabel>("CLOSED");
  const [mode, setMode] = useState<TradingMode>(getCurrentMode());
  const [uiMode, setUiMode] = useState<UiMode>(getCurrentUiMode());
  const [operations, setOperations] = useState<any>(null);

  useEffect(() => {
    const syncRole = () => {
      setRole(getCurrentRole());
      setIsAuthenticated(hasAuthToken());
    };
    const syncMode = () => setMode(getCurrentMode());
    const syncUiMode = () => setUiMode(getCurrentUiMode());

    window.addEventListener("quantgrid-role-change", syncRole);
    window.addEventListener("quantgrid-mode-change", syncMode);
    window.addEventListener("quantgrid-ui-mode-change", syncUiMode);
    window.addEventListener("storage", syncRole);
    window.addEventListener("storage", syncMode);
    return () => {
      window.removeEventListener("quantgrid-role-change", syncRole);
      window.removeEventListener("quantgrid-mode-change", syncMode);
      window.removeEventListener("quantgrid-ui-mode-change", syncUiMode);
      window.removeEventListener("storage", syncRole);
      window.removeEventListener("storage", syncMode);
    };
  }, []);

  useEffect(() => {
    if (!isAuthenticated) {
      setMarketStatus("CLOSED");
      return;
    }

    let active = true;

    const loadMarketStatus = async () => {
      try {
        const response = await api.operationsStatus();
        if (active) {
          setOperations(response);
          setMarketStatus(getMarketStatusLabel(response?.market_status));
        }
      } catch {
        if (active) setMarketStatus("CLOSED");
      }
    };

    void loadMarketStatus();
    const intervalId = window.setInterval(loadMarketStatus, 30000);

    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, [isAuthenticated]);

  const login = async (event: React.FormEvent) => {
    event.preventDefault();
    setAuthError(null);

    try {
      const response = await api.login({ username: username.trim(), password });
      const nextRole = response?.role as Role;
      const token = response?.access_token;

      if (!token || !roles.includes(nextRole)) {
        clearCurrentAuth();
        throw new Error("Login API is out of date. Redeploy the backend and try again.");
      }

      setCurrentAuth(nextRole, token);
      setRole(nextRole);
      setIsAuthenticated(true);
      setPassword("");
    } catch (error: any) {
      setAuthError(getApiErrorMessage(error, "Login failed"));
    }
  };

  const logout = () => {
    clearCurrentAuth();
    setRole("viewer");
    setIsAuthenticated(false);
  };
  const brokerConnected = Boolean(operations?.system_health?.broker?.connected);
  const systemReady = Boolean(operations?.system_health?.api?.healthy && operations?.system_health?.db?.healthy);

  return (
    <header className={`topbar ${isAuthenticated ? "topbar-authenticated" : "topbar-guest"}`}>
      <div className="topbar-title">
        <span className="topbar-eyebrow">Decision workspace</span>
        <strong>NIFTY Options</strong>
      </div>
      <div className="topbar-actions">
        <label className="topbar-search">
          <span className="sr-only">Search QuantGrid</span>
          <input type="search" placeholder="Search NIFTY, signal, setup" aria-label="Search QuantGrid" />
        </label>
        <div className="topbar-system-group" aria-label="Market and system status">
          <div className={`market-status-badge ${getMarketStatusClass(marketStatus)}`} role="status">
            <span className="status-indicator" aria-hidden="true" />
            {marketStatus}
          </div>
          <div className={`terminal-pill ${brokerConnected ? "terminal-pill-good" : "terminal-pill-muted"}`} title="Broker status">
            Broker {brokerConnected ? "Connected" : "Paper"}
          </div>
          <div className={`terminal-pill ${systemReady ? "terminal-pill-good" : "terminal-pill-warn"}`} title="System health">
            System {systemReady ? "Ready" : "Review"}
          </div>
        </div>
        {mode === "live" && (
          <div className="alert alert-error live-warning" role="alert">
            LIVE TRADING ENABLED
          </div>
        )}
        {isAuthenticated && (role === "admin" || role === "developer") && (
          <div className="workspace-controls" aria-label="Workspace controls">
            <div className="mode-toggle compact-toggle" role="group" aria-label="Interface mode">
              <button type="button" className={uiMode === "trader" ? "active" : ""} onClick={() => setCurrentUiMode("trader")}>Trader</button>
              <button type="button" className={uiMode === "developer" ? "active" : ""} onClick={() => setCurrentUiMode("developer")}>Advanced</button>
            </div>
            <div className="mode-toggle compact-toggle" role="group" aria-label="Trading mode">
              <button type="button" className={mode === "paper" ? "active" : ""} onClick={() => setCurrentMode("paper")}>Paper</button>
              <button type="button" className={mode === "live" ? "active" : ""} onClick={() => setCurrentMode("live")} title="Live mode requires HTTPS">Live</button>
            </div>
          </div>
        )}
        <button className="notification-button" type="button" aria-label="Notifications">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></svg>
          <span>Alerts</span>
        </button>
        {isAuthenticated ? (
          <div className="auth-status">
            <span className="user-avatar" aria-hidden="true">{roleLabels[role].slice(0, 1)}</span>
            <span className="auth-role">{roleLabels[role]}</span>
            <button type="button" onClick={logout} title="Sign out" aria-label="Sign out">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 17l5-5-5-5M15 12H3M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5" /></svg>
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
      </div>
    </header>
  );
}
