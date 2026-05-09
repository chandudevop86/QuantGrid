import { useEffect } from "react";

export const useLive = (onMessage: (data: any) => void) => {
  useEffect(() => {
    const ws = new WebSocket("ws://YOUR_EC2_IP:8005/ws");

    ws.onmessage = (event) => {
      onMessage(JSON.parse(event.data));
    };

    return () => ws.close();
  }, []);
};