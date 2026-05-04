import { useState } from "react";

export default function App() {
  const [signals, setSignals] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const runStrategy = async () => {
    setLoading(true);

    try {
      const res = await fetch("http://13.222.179.171:8000/trading/signals", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          strategy_name: "amd",
          symbol: "NIFTY",
          capital: 100000,
          risk_pct: 1,
          candles: [], // you can pass real data later
        }),
      });

      const data = await res.json();
      setSignals(data);
    } catch (err) {
      console.error(err);
      alert("API error");
    }

    setLoading(false);
  };

  return (
    <div style={{ padding: 20 }}>
      <h1>QuantGrid Trading UI 🚀</h1>

      <button onClick={runStrategy} disabled={loading}>
        {loading ? "Running..." : "Run AMD Strategy"}
      </button>

      <h2>Signals</h2>

      <pre>{JSON.stringify(signals, null, 2)}</pre>
    </div>
  );
}