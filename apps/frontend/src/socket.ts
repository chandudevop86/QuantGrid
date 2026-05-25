function defaultSocketUrl() {
  if (typeof window === "undefined") {
    return "ws://localhost:8000/ws";
  }

  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  if (window.location.port === "5173") {
    return `${protocol}://${window.location.hostname}:8000/ws`;
  }

  return `${protocol}://${window.location.host}/ws`;
}

export function createSocket() {
  return new WebSocket(import.meta.env.VITE_WS_URL ?? defaultSocketUrl());
}
