import { useState } from "react";

export default function App() {
  const [signals, setSignals] = useState([]);

  const runStrategy = async () => {
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
        candles: []
      }),
    });

    const data = await res.json();
    setSignals(data);
  };

  return (
    <div style={{ padding: 20 }}>
      <h1>QuantGrid 🚀</h1>

      <button onClick={runStrategy}>Run Strategy</button>

      <pre>{JSON.stringify(signals, null, 2)}</pre>
    </div>
  );
}