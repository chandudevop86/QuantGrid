import { useState } from "react";

function App() {
  const [signals, setSignals] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const runStrategy = async () => {
    setLoading(true);

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
        candles: sampleData(), // temp mock
      }),
    });

    const data = await res.json();
    setSignals(data);
    setLoading(false);
  };

  return (
    <div style={{ padding: 20 }}>
      <h1>📊 QuantGrid Trading Dashboard</h1>

      <button onClick={runStrategy}>
        {loading ? "Running..." : "Run Strategy"}
      </button>

      <table border={1} cellPadding={10} style={{ marginTop: 20 }}>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Side</th>
            <th>Entry</th>
            <th>SL</th>
            <th>Target</th>
            <th>Score</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((s, i) => (
            <tr key={i}>
              <td>{s.symbol}</td>
              <td>{s.side}</td>
              <td>{s.entry_price}</td>
              <td>{s.stop_loss}</td>
              <td>{s.target_price}</td>
              <td>{s.metadata?.score}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default App;


// TEMP DATA (replace later with real candles)
function sampleData() {
  return [
    {
      timestamp: "2024-01-01T09:15:00",
      open: 100,
      high: 105,
      low: 99,
      close: 104,
      volume: 1000,
    },
    {
      timestamp: "2024-01-01T09:20:00",
      open: 104,
      high: 108,
      low: 103,
      close: 107,
      volume: 1200,
    },
  ];
}