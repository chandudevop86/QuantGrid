import { useEffect, useState } from "react";
import { api } from "../api";
import { getApiErrorMessage } from "../api/client";
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
  const [operations, setOperations] = useState<any>(null);

  useEffect(() => {
    const syncRole = () => {
      setRole(getCurrentRole());
      setIsAuthenticated(hasAuthToken());
    };
    window.addEventListener("quantgrid-role-change", syncRole);
    window.addEventListener("storage", syncRole);
    return () => {
      window.removeEventListener("quantgrid-role-change", syncRole);
      window.removeEventListener("storage", syncRole);
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
        <strong>NIFTY Options Decision Assistant</strong>
        <span>Buy CE, Buy PE, or No Trade</span>
      </div>
      <div className="topbar-actions">
        <label className="topbar-search">
          <span className="sr-only">Search QuantGrid</span>
          <input type="search" placeholder="Search NIFTY, signal, setup" aria-label="Search QuantGrid" />
        </label>
        <div className={`market-status-badge ${getMarketStatusClass(marketStatus)}`} role="status">
          {marketStatus}
        </div>
        <div className={`terminal-pill ${brokerConnected ? "terminal-pill-good" : "terminal-pill-muted"}`} title="Broker status">
          Broker {brokerConnected ? "Connected" : "Paper"}
        </div>
        <div className={`terminal-pill ${systemReady ? "terminal-pill-good" : "terminal-pill-warn"}`} title="System health">
          System {systemReady ? "Ready" : "Review"}
        </div>
        <button className="notification-button" type="button" aria-label="Notifications">
          Alerts
        </button>
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
      </div>
    </header>
  );
}
