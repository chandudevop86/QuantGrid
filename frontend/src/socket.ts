function defaultSocketUrl() {
  if (typeof window === "undefined") {
    return "ws://localhost:8005/ws";
  }

  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  if (!window.location.port || window.location.port === "80" || window.location.port === "443") {
    return `${protocol}://${window.location.host}/ws`;
  }

  return `${protocol}://${window.location.hostname}:8005/ws`;
}

export function createSocket() {
  return new WebSocket(import.meta.env.VITE_WS_URL ?? defaultSocketUrl());
}
