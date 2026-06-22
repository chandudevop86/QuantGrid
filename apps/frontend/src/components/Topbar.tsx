import { useEffect, useState } from "react";
import { api } from "../api";
import { getApiErrorMessage } from "../api/client";
import {
  getCurrentMode,
  getCurrentUiMode,
  modeLabels,
  modes,
  setCurrentMode,
  setCurrentUiMode,
  isInsecureRemoteHttp,
  type TradingMode,
  type UiMode,
  uiModeLabels,
  uiModes,
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
  const [mode, setMode] = useState<TradingMode>(getCurrentMode());
  const [uiMode, setUiMode] = useState<UiMode>(getCurrentUiMode());
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(hasAuthToken());
  const [marketStatus, setMarketStatus] = useState<MarketStatusLabel>("CLOSED");
  const [brokerCircuit, setBrokerCircuit] = useState<any>(null);
  const insecureHttp = isInsecureRemoteHttp();

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
    window.addEventListener("storage", syncUiMode);
    return () => {
      window.removeEventListener("quantgrid-role-change", syncRole);
      window.removeEventListener("quantgrid-mode-change", syncMode);
      window.removeEventListener("quantgrid-ui-mode-change", syncUiMode);
      window.removeEventListener("storage", syncRole);
      window.removeEventListener("storage", syncMode);
      window.removeEventListener("storage", syncUiMode);
    };
  }, []);

  useEffect(() => {
    if (!isAuthenticated) {
      setMarketStatus("CLOSED");
      setBrokerCircuit(null);
      return;
    }

    let active = true;

    const loadMarketStatus = async () => {
      try {
        const [response, circuit] = await Promise.all([
          api.operationsStatus(),
          api.brokerCircuitBreakerStatus().catch(() => null),
        ]);
        if (active) setMarketStatus(getMarketStatusLabel(response?.market_status));
        if (active) setBrokerCircuit(circuit);
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

  const changeMode = (nextMode: TradingMode) => {
    if (nextMode === "live" && insecureHttp) {
      setCurrentMode("paper");
      setMode("paper");
      return;
    }
    setCurrentMode(nextMode);
    setMode(nextMode);
  };

  const changeUiMode = (nextMode: UiMode) => {
    setCurrentUiMode(nextMode);
    setUiMode(nextMode);
  };

  return (
    <header className={`topbar ${isAuthenticated ? "topbar-authenticated" : "topbar-guest"}`}>
      <div className="topbar-title">
        <strong>Trading Dashboard</strong>
        <span>Service health and execution overview</span>
      </div>
      {brokerCircuit?.active && (
        <div className="topbar-broker-circuit-warning" role="alert">
          BROKER CIRCUIT BREAKER ACTIVE
        </div>
      )}
      <div className="topbar-actions">
        <div className={`market-status-badge ${getMarketStatusClass(marketStatus)}`} role="status">
          {marketStatus}
        </div>
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
              disabled={item === "live" && insecureHttp}
              title={item === "live" && insecureHttp ? "Live trading requires HTTPS." : undefined}
              onClick={() => changeMode(item)}
            >
              {modeLabels[item]}
            </button>
          ))}
        </div>
        {mode === "live" && (
          <div className="topbar-live-warning" role="alert">
            LIVE TRADING ENABLED
          </div>
        )}
        <div className="mode-toggle" aria-label="Dashboard mode">
          {uiModes.map((item) => (
            <button
              key={item}
              type="button"
              className={uiMode === item ? "active" : ""}
              onClick={() => changeUiMode(item)}
            >
              {uiModeLabels[item]}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}
