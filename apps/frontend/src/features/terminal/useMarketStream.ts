import { useEffect, useRef, useState } from "react";
import { createSocket } from "../../socket";
import type { MarketStreamEvent } from "./types";

export type MarketStreamStatus = "connecting" | "connected" | "offline";

/**
 * Maintains the authenticated QuantGrid WebSocket connection.
 *
 * The current FastAPI socket publishes dashboard-status events, not per-symbol
 * quote/candle subscriptions. Keeping that boundary explicit prevents the UI from
 * reporting a fake market stream. Candle and LTP freshness stay owned by React
 * Query's documented HTTP endpoints until the backend exposes market channels.
 */
export function useMarketStream() {
  const [status, setStatus] = useState<MarketStreamStatus>("connecting");
  const reconnectTimer = useRef<number>();

  useEffect(() => {
    let socket: WebSocket | null = null;
    let cancelled = false;
    let attempts = 0;

    const connect = () => {
      if (cancelled) return;
      setStatus("connecting");
      try {
        socket = createSocket();
        socket.onopen = () => {
          attempts = 0;
          setStatus("connected");
        };
        socket.onmessage = (event) => {
          try {
            window.dispatchEvent(new CustomEvent<MarketStreamEvent>("quantgrid:market", { detail: JSON.parse(event.data) }));
          } catch {
            // Ignore malformed server frames; the HTTP data path remains available.
          }
        };
        socket.onclose = () => {
          if (cancelled) return;
          setStatus("offline");
          const delay = Math.min(15_000, 1_000 * 2 ** attempts++);
          reconnectTimer.current = window.setTimeout(connect, delay);
        };
        socket.onerror = () => socket?.close();
      } catch {
        setStatus("offline");
      }
    };

    connect();
    return () => {
      cancelled = true;
      if (reconnectTimer.current) window.clearTimeout(reconnectTimer.current);
      socket?.close();
    };
  }, []);

  return status;
}
