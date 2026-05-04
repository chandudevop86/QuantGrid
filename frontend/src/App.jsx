import { useState } from "react";

const API = "http://13.222.179.171:8000";

export default function App() {
  const [strategy, setStrategy] = useState("amd");
  const [capital, setCapital] = useState(100000);
  const [risk, setRisk] = useState(1);
  const [rr, setRR] = useState(2);
  const [signals, setSignals] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const runStrategy = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/trading/signals`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          strategy_name: strategy,
          symbol: "NIFTY",
          capital: capital,
          risk_pct: risk,
          rr_ratio: rr,
          candles: [], // later connect real data
        }),
      });

      const data = await res.json();
      setSignals(data);
    } catch (err) {
      console.error(err);
      alert("Backend error");
    }
    setLoading(false);
  };

  return (
    <div style={{ padding: 20, fontFamily: "Arial" }}>
      <h1>📊 QuantGrid Trading Dashboard</h1>

      {/* Controls */}
      <div style={{ display: "flex", gap: 10, marginBottom: 20 }}>
        <select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
          <option value="amd">AMD Strategy</option>
          <option value="breakout">Breakout</option>
          <option value="mean_reversion">Mean Reversion</option>
        </select>

        <input
          type="number"
          value={capital}
          onChange={(e) => setCapital(Number(e.target.value))}
          placeholder="Capital"
        />

        <input
          type="number"
          value={risk}
          onChange={(e) => setRisk(Number(e.target.value))}
          placeholder="Risk %"
        />

        <input
          type="number"
          value={rr}
          onChange={(e) => setRR(Number(e.target.value))}
          placeholder="RR Ratio"
        />

        <button onClick={runStrategy}>
          {loading ? "Running..." : "Run"}
        </button>
      </div>

      {/* Signals Table */}
      <h2>📈 Signals</h2>

      <table border={1} cellPadding={8}>
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