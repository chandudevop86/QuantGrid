import { useEffect } from "react";
import { createSocket } from "../socket";

export const useLive = (onMessage: (data: any) => void) => {
  useEffect(() => {
    const ws = createSocket();

    ws.onopen = () => {};

    ws.onmessage = (event) => {
      onMessage(JSON.parse(event.data));
    };

    ws.onclose = () => {};

    return () => ws.close();
  }, []);
};
