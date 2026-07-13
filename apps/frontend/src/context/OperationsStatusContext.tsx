import { createContext, useContext, useEffect, useMemo, useState } from "react";

import { api } from "../api";
import { hasAuthToken } from "../roles";
import { createSocket } from "../socket";

type OperationsStatusValue = {
  operations: any;
  loading: boolean;
  error: string | null;
  socketStatus: "online" | "offline" | "polling";
  refresh: () => Promise<void>;
};

const OperationsStatusContext = createContext<OperationsStatusValue | null>(null);

export function OperationsStatusProvider({ children }: { children: React.ReactNode }) {
  const [authenticated, setAuthenticated] = useState(hasAuthToken());
  const [operations, setOperations] = useState<any>(null);
  const [loading, setLoading] = useState(authenticated);
  const [error, setError] = useState<string | null>(null);
  const [socketStatus, setSocketStatus] = useState<OperationsStatusValue["socketStatus"]>("offline");

  const refresh = async () => {
    if (!hasAuthToken()) return;
    try {
      setOperations(await api.operationsStatus());
      setError(null);
    } catch {
      setError("Dashboard status is unavailable.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const syncAuth = () => setAuthenticated(hasAuthToken());
    window.addEventListener("quantgrid-role-change", syncAuth);
    window.addEventListener("storage", syncAuth);
    return () => {
      window.removeEventListener("quantgrid-role-change", syncAuth);
      window.removeEventListener("storage", syncAuth);
    };
  }, []);

  useEffect(() => {
    if (!authenticated) {
      setOperations(null);
      setLoading(false);
      setError(null);
      setSocketStatus("offline");
      return;
    }

    let active = true;
    let fallbackId: number | null = null;
    const socket = createSocket();
    const poll = () => { if (active) void refresh(); };
    const startFallback = () => {
      if (fallbackId !== null) return;
      setSocketStatus("polling");
      fallbackId = window.setInterval(poll, 15000);
    };

    setLoading(true);
    poll();
    socket.onopen = () => {
      setSocketStatus("online");
      if (fallbackId !== null) window.clearInterval(fallbackId);
      fallbackId = null;
    };
    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message?.type === "dashboard_status" && message?.payload) {
          setOperations(message.payload);
          setError(null);
          setLoading(false);
        }
      } catch {
        setError("Received an invalid dashboard status update.");
      }
    };
    socket.onerror = () => socket.close();
    socket.onclose = () => {
      if (!active) return;
      setSocketStatus("offline");
      startFallback();
    };

    return () => {
      active = false;
      if (fallbackId !== null) window.clearInterval(fallbackId);
      socket.close();
    };
  }, [authenticated]);

  const value = useMemo(
    () => ({ operations, loading, error, socketStatus, refresh }),
    [operations, loading, error, socketStatus],
  );
  return <OperationsStatusContext.Provider value={value}>{children}</OperationsStatusContext.Provider>;
}

export function useOperationsStatus() {
  const value = useContext(OperationsStatusContext);
  if (!value) throw new Error("useOperationsStatus must be used inside OperationsStatusProvider");
  return value;
}
