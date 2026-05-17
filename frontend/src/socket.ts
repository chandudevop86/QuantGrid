function defaultSocketUrl() {
  if (typeof window === "undefined") {
    return "ws://13.222.179.171:8005/ws";
  }

  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.hostname}:8005/ws`;
}

export function createSocket() {
  return new WebSocket(import.meta.env.VITE_WS_URL ?? defaultSocketUrl());
}
