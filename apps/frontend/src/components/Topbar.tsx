import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
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
  canAccessRoute,
  getCurrentRole,
  hasAuthToken,
  roleLabels,
  roles,
  setCurrentAuth,
  type Role,
} from "../roles";
import { getMarketStatusClass, getMarketStatusLabel, type MarketStatusLabel } from "../utils/marketStatus";

export default function Topbar() {
  const navigate = useNavigate();
  const [role, setRole] = useState<Role>(getCurrentRole());
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(hasAuthToken());
  const [marketStatus, setMarketStatus] = useState<MarketStatusLabel>("CLOSED");
  const [mode, setMode] = useState<TradingMode>(getCurrentMode());
  const [uiMode, setUiMode] = useState<UiMode>(getCurrentUiMode());
  const [operations, setOperations] = useState<any>(null);
  const [brokerStatus, setBrokerStatus] = useState<any>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [showAlerts, setShowAlerts] = useState(false);

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
      setBrokerStatus(null);
      return;
    }

    let active = true;

    const loadMarketStatus = async () => {
      const [operationsResult, brokerResult] = await Promise.allSettled([
        api.operationsStatus(),
        api.brokerStatus(),
      ]);
      if (!active) return;

      if (operationsResult.status === "fulfilled") {
        setOperations(operationsResult.value);
        setMarketStatus(getMarketStatusLabel(operationsResult.value?.market_status));
      } else {
        setMarketStatus("CLOSED");
      }
      if (brokerResult.status === "fulfilled") {
        setBrokerStatus(brokerResult.value);
      } else {
        setBrokerStatus({
          connected: false,
          error: "status_unavailable",
          message: "Broker status could not be verified.",
        });
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
  const brokerConnected = Boolean(brokerStatus?.connected);
  const brokerAlert = brokerConnected
    ? null
    : brokerStatus?.error === "token_expired"
      ? "Dhan access token expired. Save a fresh token in Broker Login; orders remain in paper mode."
      : brokerStatus?.message || "Broker is not connected; orders remain in paper mode.";
  const systemReady = Boolean(operations?.system_health?.api?.healthy && operations?.system_health?.db?.healthy);
  const searchableRoutes = [
    ["Market decision overview", "/"], ["Options market chain", "/market"], ["Qualified setups signals", "/signals"],
    ["Paper portfolio positions", "/paper-trades"], ["Backtest results", "/history"], ["Risk controls", "/settings"],
    ["Live analysis", "/analysis"], ["Order ticket", "/trade"], ["Execution", "/execution"],
    ["Strategies", "/strategies"], ["Operations", "/operations"], ["Security", "/security"],
    ["Candles", "/candles"], ["Market copilot", "/copilot"], ["Jobs", "/jobs"],
    ["Institutional", "/institutional"], ["Investing", "/investing"], ["Trading engine", "/trading-engine"],
  ] as const;
  const availableRoutes = searchableRoutes.filter(([, path]) => canAccessRoute(role, path));
  const submitSearch = (event: React.FormEvent) => {
    event.preventDefault();
    const query = searchQuery.trim().toLowerCase();
    if (!query) return;
    const match = availableRoutes.find(([label, path]) => label.toLowerCase().includes(query) || path.includes(query));
    if (match) {
      navigate(match[1]);
      setSearchQuery("");
    }
  };
  const alerts = [
    !systemReady ? "System health requires review." : null,
    brokerAlert,
    marketStatus !== "LIVE" ? `Market status is ${marketStatus.toLowerCase()}.` : null,
    mode === "live" ? "Live trading mode is enabled." : null,
  ].filter(Boolean) as string[];

  return (
    <header className={`topbar ${isAuthenticated ? "topbar-authenticated" : "topbar-guest"}`}>
      <div className="topbar-title">
        <span className="topbar-eyebrow">Decision workspace</span>
        <strong>NIFTY Options</strong>
      </div>
      <div className="topbar-actions">
        {isAuthenticated && <>
        <form className="topbar-search" onSubmit={submitSearch} role="search">
          <label className="sr-only" htmlFor="quantgrid-search">Search QuantGrid</label>
          <input id="quantgrid-search" type="search" list="quantgrid-search-routes" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="Go to decision, options, risk..." aria-label="Search QuantGrid" />
          <datalist id="quantgrid-search-routes">
            {availableRoutes.map(([label, path]) => <option key={path} value={label} />)}
          </datalist>
        </form>
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
        <div className="notification-menu">
        <button className="notification-button" type="button" aria-label={`Notifications, ${alerts.length} active`} aria-expanded={showAlerts} onClick={() => setShowAlerts((current) => !current)}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></svg>
          <span>Alerts</span>
          {alerts.length > 0 && <small className="notification-count">{alerts.length}</small>}
        </button>
        {showAlerts && (
          <div className="notification-popover" role="status">
            <div className="notification-popover-header"><strong>System alerts</strong><span>{alerts.length} active</span></div>
            {alerts.length ? alerts.map((alert) => <p key={alert}>{alert}</p>) : <p className="notification-empty">No active alerts. Systems look ready.</p>}
          </div>
        )}
        </div>
        </>}
        {isAuthenticated ? (
          <div className="auth-status">
            <span className="user-avatar" aria-hidden="true">{roleLabels[role].slice(0, 1)}</span>
            <span className="auth-role">{roleLabels[role]}</span>
            <button type="button" onClick={logout} title="Sign out" aria-label="Sign out">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 17l5-5-5-5M15 12H3M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5" /></svg>
            </button>
          </div>
        ) : (
          <form className="auth-form" id="quantgrid-login" onSubmit={login}>
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
