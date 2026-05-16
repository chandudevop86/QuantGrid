const socketUrl = import.meta.env.VITE_WS_URL ?? "ws://localhost:8005/ws";

export function createSocket() {
  return new WebSocket(socketUrl);
}
