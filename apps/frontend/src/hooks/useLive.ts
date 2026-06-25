import { useEffect } from "react";
import { createSocket } from "../socket";
import { api } from "../api";

export const useLive = (onMessage: (data: any) => void) => {
  useEffect(() => {
    let ws: WebSocket | null = null;
    let stopped = false;
    let reconnectAttempts = 0;
    let reconnectTimer: number | null = null;
    let pollingTimer: number | null = null;
    const maxReconnectAttempts = 5;

    const startPolling = () => {
      if (pollingTimer !== null) return;
      pollingTimer = window.setInterval(() => {
        api.operationsStatus()
          .then((payload) => onMessage({ type: "dashboard_status", payload }))
          .catch(() => {});
      }, 15000);
    };

    const connect = () => {
      if (stopped) return;
      ws = createSocket();

      ws.onopen = () => {
        reconnectAttempts = 0;
        if (pollingTimer !== null) {
          window.clearInterval(pollingTimer);
          pollingTimer = null;
        }
      };

      ws.onmessage = (event) => {
        onMessage(JSON.parse(event.data));
      };

      ws.onerror = () => {
        ws?.close();
      };

      ws.onclose = () => {
        if (stopped) return;
        reconnectAttempts += 1;
        if (reconnectAttempts > maxReconnectAttempts) {
          startPolling();
          return;
        }
        const delay = Math.min(30000, 1000 * 2 ** (reconnectAttempts - 1));
        reconnectTimer = window.setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      stopped = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      if (pollingTimer !== null) window.clearInterval(pollingTimer);
      ws?.close();
    };
  }, []);
};
