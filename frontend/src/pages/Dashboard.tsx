

import { useEffect, useState } from "react";

export default function LiveAnalysis() {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    const ws = new WebSocket("ws://localhost:8005/ws");

    ws.onmessage = (e) => {
      const parsed = JSON.parse(e.data);
      console.log("LIVE:", parsed);
      setData(parsed);
    };

    ws.onopen = () => {
      console.log("WebSocket connected");
    };

    ws.onerror = (err) => {
      console.error("WebSocket error:", err);
    };

    ws.onclose = () => {
      console.log("WebSocket disconnected");
    };

    // cleanup (VERY IMPORTANT)
    return () => {
      ws.close();
    };
  }, []);

  return (
    <div>
      <h1>Live Analysis</h1>

      {data ? (
        <div>
          <p>Order ID: {data.order_id}</p>
          <p>Status: {data.status}</p>
        </div>
      ) : (
        <p>Waiting for live data...</p>
      )}
    </div>
  );
}