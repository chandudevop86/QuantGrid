function defaultSocketUrl() {
  if (typeof window === "undefined") {
    return "ws://localhost:8000/ws";
  }

  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  if (import.meta.env.DEV) {
    return `${protocol}://${window.location.host}/ws`;
  }

  return `${protocol}://${window.location.host}/ws`;
}

function normalizeSocketUrl(socketUrl: string | undefined) {
  if (!socketUrl || typeof window === "undefined") return socketUrl;

  try {
    const target = new URL(socketUrl, window.location.origin);
    const isSameHost = target.hostname === window.location.hostname;
    const isBackendPort = target.port === "8000";

    if (!import.meta.env.DEV && isSameHost && (isBackendPort || target.pathname === "/ws")) {
      return defaultSocketUrl();
    }
  } catch {
    return socketUrl;
  }

  return socketUrl;
}

export function createSocket() {
  return new WebSocket(normalizeSocketUrl(import.meta.env.VITE_WS_URL) ?? defaultSocketUrl());
}
