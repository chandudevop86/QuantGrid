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
