import { useEffect, useRef, useState } from "react";
import { createSocket } from "../../socket";
import type { MarketStreamEvent } from "./types";

/** Protocol boundary for streaming quotes/candles with bounded reconnect backoff. */
export function useMarketStream(symbol: string) {
  const [status, setStatus] = useState<"connecting" | "live" | "offline">("connecting");
  const timer = useRef<number>();
  useEffect(() => {
    let socket: WebSocket | null = null; let cancelled = false;
    const connect = () => {
      if (cancelled) return; setStatus("connecting");
      try {
        socket = createSocket();
        socket.onopen = () => { setStatus("live"); socket?.send(JSON.stringify({ action: "subscribe", channels: ["quotes", "candles"], symbol })); };
        socket.onmessage = (event) => { try { window.dispatchEvent(new CustomEvent<MarketStreamEvent>("quantgrid:market", { detail: JSON.parse(event.data) })); } catch { /* Drop malformed frames. */ } };
        socket.onclose = () => { if (!cancelled) { setStatus("offline"); timer.current = window.setTimeout(connect, 2_000); } };
        socket.onerror = () => socket?.close();
      } catch { setStatus("offline"); }
    };
    connect();
    return () => { cancelled = true; if (timer.current) window.clearTimeout(timer.current); socket?.close(); };
  }, [symbol]);
  return status;
}
