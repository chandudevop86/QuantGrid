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

export default function Topbar() {
  const [role, setRole] = useState<Role>(getCurrentRole());
  const [mode, setMode] = useState<TradingMode>(getCurrentMode());
  const [uiMode, setUiMode] = useState<UiMode>(getCurrentUiMode());
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(hasAuthToken());
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<Role>("viewer");
  const [userMessage, setUserMessage] = useState<string | null>(null);

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
    setCurrentMode(nextMode);
    setMode(nextMode);
  };

  const changeUiMode = (nextMode: UiMode) => {
    setCurrentUiMode(nextMode);
    setUiMode(nextMode);
  };

  const createUser = async (event: React.FormEvent) => {
    event.preventDefault();
    setUserMessage(null);

    try {
      const created = await api.createUser({
        username: newUsername,
        password: newPassword,
        role: newRole,
      });
      setUserMessage(`Created ${created.username} as ${roleLabels[created.role as Role]}.`);
      setNewUsername("");
      setNewPassword("");
      setNewRole("viewer");
    } catch (error: any) {
      setUserMessage(error?.response?.data?.detail ?? error?.message ?? "User creation failed");
    }
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
      {isAuthenticated && role === "admin" && (
        <form className="create-user-form" onSubmit={createUser}>
          <input
            value={newUsername}
            onChange={(event) => setNewUsername(event.target.value)}
            placeholder="New username"
            aria-label="New username"
          />
          <input
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            placeholder="New password"
            type="password"
            aria-label="New password"
          />
          <select
            value={newRole}
            onChange={(event) => setNewRole(event.target.value as Role)}
            aria-label="New user role"
          >
            {roles.map((item) => (
              <option key={item} value={item}>
                {roleLabels[item]}
              </option>
            ))}
          </select>
          <button type="submit">Create User</button>
          {userMessage && <span>{userMessage}</span>}
        </form>
      )}
    </header>
  );
}
