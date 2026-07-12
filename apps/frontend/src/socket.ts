function defaultSocketUrl() {
  if (typeof window === "undefined") {
    return "ws://localhost:8000/ws";
  }

  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  if (import.meta.env.DEV) {
    const backendHost = import.meta.env.VITE_WS_BACKEND_HOST ?? `${window.location.hostname}:8000`;
    return `${protocol}://${backendHost}/ws`;
  }

  return `${protocol}://${window.location.host}/ws`;
}

function normalizeSocketUrl(socketUrl: string | undefined) {
  if (!socketUrl || typeof window === "undefined") return socketUrl;

  try {
    const target = new URL(socketUrl, window.location.origin);
    const isSameHost = target.hostname === window.location.hostname;
    const isBackendPort = target.port === "8000";
    const browserIsRemote = !["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
    const targetIsLoopback = ["localhost", "127.0.0.1", "::1"].includes(target.hostname);

    if (browserIsRemote && targetIsLoopback) {
      return defaultSocketUrl();
    }

    if (!import.meta.env.DEV && isSameHost && (isBackendPort || target.pathname === "/ws")) {
      return defaultSocketUrl();
    }
  } catch {
    return socketUrl;
  }

  return socketUrl;
}

export function createSocket() {
  const socketUrl = normalizeSocketUrl(import.meta.env.VITE_WS_URL) ?? defaultSocketUrl();
  const target = new URL(socketUrl, typeof window === "undefined" ? undefined : window.location.origin);
  const token = getAuthToken();
  return token
    ? new WebSocket(target.toString(), ["quantgrid", token])
    : new WebSocket(target.toString());
}
import { getAuthToken } from "./roles";
