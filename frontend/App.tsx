import { useEffect, useState } from "react";

function App() {
  const [strategies, setStrategies] = useState<string[]>([]);
  const [selected, setSelected] = useState("");
  const [signals, setSignals] = useState<any[]>([]);

  useEffect(() => {
    fetch("http://13.222.179.171:8000/trading/strategies")
      .then(res => res.json())
      .then(setStrategies);
  }, []);

  const runStrategy = async () => {
    const res = await fetch("http://13.222.179.171:8000/trading/signals", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        strategy_name: selected,
        symbol: "NIFTY",
        capital: 100000,
        risk_pct: 1,
        rr_ratio: 2,
        candles: []
      })
    });

    const data = await res.json();
    setSignals(data);
  };

  return (
    <div style={{ padding: 20 }}>
      <h1>🚀 QuantGrid Pro Dashboard</h1>

      <h3>Select Strategy</h3>
      <select onChange={(e) => setSelected(e.target.value)}>
        <option>Select</option>
        {strategies.map((s) => (
          <option key={s}>{s}</option>
        ))}
      </select>

      <br /><br />
      <button onClick={runStrategy}>Run Strategy</button>

      <h3>Signals</h3>
      <table border={1} cellPadding={10}>
        <thead>
          <tr>
            <th>Type</th>
            <th>Entry</th>
            <th>SL</th>
            <th>Target</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((s, i) => (
            <tr key={i}>
              <td>{s.type}</td>
              <td>{s.entry}</td>
              <td>{s.stop_loss}</td>
              <td>{s.target}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default App;