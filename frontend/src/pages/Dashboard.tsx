import { useEffect, useState } from "react";
import { api } from "../api";

export default function Dashboard() {
  const [summary, setSummary] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getSummary()
      .then(setSummary)
      .catch(() => setError("Dashboard API is not available yet."));
  }, []);

  return (
    <section>
      <h1>QuantGrid Dashboard</h1>
      {error && <p style={{ color: "#f87171" }}>{error}</p>}
      <pre style={{ background: "#0f172a", padding: 16, borderRadius: 8 }}>
        {summary ? JSON.stringify(summary, null, 2) : "Waiting for dashboard data..."}
      </pre>
    </section>
  );
}

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




import { useEffect } from "react";
import { api } from "../api";

export default function Dashboard() {
  useEffect(() => {
    const fetchData = async () => {
      const price = await api.getPrice();
      console.log("Live price:", price);
    };

    fetchData();
  }, []);

  return <div>Dashboard</div>;
}
