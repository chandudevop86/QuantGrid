import { useEffect, useState } from "react";
import { api } from "../services/api";

export default function Dashboard() {
  const [health, setHealth] = useState<any>({});
  const [summary, setSummary] = useState<any>({});

  useEffect(() => {
    api.health().then(setHealth);
    api.dashboard().then(setSummary);
  }, []);

  return (
    <div>
      <h2>System Health</h2>
      <pre>{JSON.stringify(health, null, 2)}</pre>

      <h2>Dashboard</h2>
      <pre>{JSON.stringify(summary, null, 2)}</pre>
    </div>
  );
}