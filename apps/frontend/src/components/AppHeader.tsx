import { useEffect, useState } from "react";
import { api } from "../api";
import { getCurrentMode, setCurrentMode, type TradingMode } from "../mode";
import { clearCurrentAuth, getCurrentRole, hasAuthToken, roleLabels, roles, setCurrentAuth, type Role } from "../roles";
import { useOperationsStatus } from "../context/OperationsStatusContext";
import { getMarketStatusLabel } from "../utils/marketStatus";
import AlertPopover from "./AlertPopover";
import StatusBadge from "./StatusBadge";
import { marketInstruments, useMarketSelection, type MarketSymbol } from "../context/MarketSelectionContext";

export default function AppHeader({ onMenuToggle }: { onMenuToggle: () => void }) {
  const { operations } = useOperationsStatus();
  const { symbol, selectSymbol } = useMarketSelection();
  const [role, setRole] = useState<Role>(getCurrentRole());
  const [authenticated, setAuthenticated] = useState(hasAuthToken());
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);
  const [mode, setMode] = useState<TradingMode>(getCurrentMode());
  const [brokerConnected, setBrokerConnected] = useState<boolean | null>(null);
  const [brokerMessage, setBrokerMessage] = useState("Broker is disconnected; orders remain in paper mode.");
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [userOpen, setUserOpen] = useState(false);

  useEffect(() => {
    const syncAuth = () => { setRole(getCurrentRole()); setAuthenticated(hasAuthToken()); };
    const syncMode = () => setMode(getCurrentMode());
    window.addEventListener("quantgrid-role-change", syncAuth);
    window.addEventListener("quantgrid-mode-change", syncMode);
    window.addEventListener("storage", syncAuth);
    return () => { window.removeEventListener("quantgrid-role-change", syncAuth); window.removeEventListener("quantgrid-mode-change", syncMode); window.removeEventListener("storage", syncAuth); };
  }, []);

  useEffect(() => {
    if (!authenticated) { setBrokerConnected(null); return; }
    if (!(["admin", "developer", "trader", "ops"] as Role[]).includes(role)) {
      setBrokerConnected(null);
      setBrokerMessage("Broker status is restricted for this role.");
      return;
    }
    let active = true;
    const load = async () => {
      try {
        const status = await api.brokerStatus();
        if (!active) return;
        setBrokerConnected(Boolean(status?.connected));
        setBrokerMessage(status?.message || (status?.connected ? "Broker connected." : "Broker is disconnected; orders remain in paper mode."));
      } catch { if (active) { setBrokerConnected(false); setBrokerMessage("Broker status is unavailable; orders remain in paper mode."); } }
    };
    void load();
    const interval = window.setInterval(load, 30000);
    return () => { active = false; window.clearInterval(interval); };
  }, [authenticated, role]);

  const login = async (event: React.FormEvent) => {
    event.preventDefault(); setAuthError(null);
    try {
      const response = await api.login({ username: username.trim(), password });
      if (!response?.access_token || !roles.includes(response.role as Role)) throw new Error("Login response is invalid.");
      setCurrentAuth(response.role as Role, response.access_token); setRole(response.role); setAuthenticated(true); setPassword("");
    } catch (error: any) { clearCurrentAuth(); setAuthError(error?.response?.data?.detail ?? error?.message ?? "Login failed."); }
  };
  const marketStatus = getMarketStatusLabel(operations?.market_status);
  const systemReady = Boolean(operations?.system_health?.api?.healthy && operations?.system_health?.db?.healthy);
  const alerts = [brokerConnected === false ? brokerMessage : null, marketStatus !== "LIVE" ? `Market is ${marketStatus.toLowerCase()}.` : null, !systemReady ? "System health requires review." : null, mode === "live" ? "Live trading mode is enabled." : null].filter(Boolean) as string[];

  if (!authenticated) return <header className="qg-app-header qg-login-header"><div className="qg-header-brand"><img src="/quantgrid-logo.svg" alt="" /><strong>QuantGrid</strong></div><form onSubmit={login}><input aria-label="Username" value={username} onChange={(event) => setUsername(event.target.value)} placeholder="Username" /><input aria-label="Password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Password" type="password" /><button type="submit">Login</button>{authError && <span role="alert">{authError}</span>}</form></header>;

  return (
    <header className="qg-app-header">
      <button type="button" className="qg-menu-button" onClick={onMenuToggle} aria-label="Toggle navigation">☰</button>
      <div className="qg-header-brand"><img src="/quantgrid-logo.svg" alt="" /><strong>QuantGrid</strong></div>
      <label className="qg-header-market">
        <span>Selected market</span>
        <select aria-label="Selected market or instrument" value={symbol} onChange={(event) => selectSymbol(event.target.value as MarketSymbol)}>
          {marketInstruments.map((instrument) => <option key={instrument.symbol} value={instrument.symbol}>{instrument.label}</option>)}
        </select>
      </label>
      <div className="qg-header-actions">
        <span className="qg-header-status qg-market-status"><StatusBadge tone={marketStatus === "LIVE" ? "positive" : "neutral"}><span className="qg-status-prefix">Market </span>{marketStatus === "LIVE" ? "Open" : "Closed"}</StatusBadge></span>
        <span className="qg-header-status qg-broker-status"><StatusBadge tone={brokerConnected === true ? "positive" : brokerConnected === false ? "danger" : "neutral"}><span className="qg-status-prefix">Broker </span>{brokerConnected === true ? "Connected" : brokerConnected === false ? "Disconnected" : "Restricted"}</StatusBadge></span>
        <div className="qg-mode-control" role="group" aria-label="Trading mode"><button type="button" className={mode === "paper" ? "active" : ""} onClick={() => setCurrentMode("paper")}>Paper</button><button type="button" className={mode === "live" ? "active live" : ""} onClick={() => setCurrentMode("live")}>Live</button></div>
        <AlertPopover alerts={alerts} open={alertsOpen} onToggle={() => setAlertsOpen((value) => !value)} />
        <div className="qg-user-menu"><button type="button" className="qg-header-button" aria-expanded={userOpen} onClick={() => setUserOpen((value) => !value)}><span className="qg-user-avatar">{roleLabels[role][0]}</span><span>{roleLabels[role]}</span></button>{userOpen && <div className="qg-user-popover"><strong>{roleLabels[role]}</strong><span>Authenticated session</span><button type="button" onClick={() => { clearCurrentAuth(); setAuthenticated(false); }}>Sign out</button></div>}</div>
      </div>
    </header>
  );
}
