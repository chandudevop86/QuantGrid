
import { useEffect, useState } from "react";

export default function Dashboard() {
  const [strategies, setStrategies] = useState<string[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("http://13.222.179.171:8000/trading/strategies")
      .then((res) => {
        if (!res.ok) throw new Error("API error");
        return res.json();
      })
      .then(setStrategies)
      .catch(() => setError("Backend not reachable"));
  }, []);

  return (
    <div>
      <h1 className="text-xl font-bold mb-4">Strategies</h1>

      {error && <p className="text-red-500">{error}</p>}

      <ul>
        {strategies.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ul>
    </div>
  );
}