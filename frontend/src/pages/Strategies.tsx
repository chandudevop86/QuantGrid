import { useState } from "react";
import { useAutoSignals } from "../hooks/useAutoSignals";

export default function Strategies() {
  const [selectedStrategy, setSelectedStrategy] = useState<string | null>(null);

  const { signal, loading } = useAutoSignals(selectedStrategy, 5000);

  const strategies = [
    "amd",
    "breakout",
    "btst",
    "mean_reversion",
    "mtf",
    "supply_demand"
  ];

  return (
    <div style={{ padding: 20 }}>
      <h1>🚀 QuantGrid Dashboard</h1>

      {/* STRATEGIES */}
      <h2>Strategies</h2>

      {strategies.map((s) => (
        <button
          key={s}
          onClick={() => setSelectedStrategy(s)}
          style={{
            display: "block",
            marginBottom: 8,
            padding: 8
          }}
        >
          {s}
        </button>
      ))}

      {/* LIVE PANEL */}
      <h2>📡 Live Signal</h2>

      {!selectedStrategy && <p>Select a strategy</p>}

      {selectedStrategy && (
        <div>
          <p>Active: {selectedStrategy}</p>
          <p>Status: {loading ? "Updating..." : "Live"}</p>

          <pre>
            {JSON.stringify(signal, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}