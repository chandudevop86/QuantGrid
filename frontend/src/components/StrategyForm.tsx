import { useEffect, useState } from "react";
import { api } from "../services/api";

export default function StrategyForm() {
  const [strategies, setStrategies] = useState<string[]>([]);
  const [selected, setSelected] = useState("");
  const [result, setResult] = useState<any>(null);

  useEffect(() => {
    api.strategies().then(setStrategies);
  }, []);

  const run = async () => {
    const res = await api.runSignals({
      strategy_name: selected,
      symbol: "NIFTY",
      capital: 100000,
      risk_pct: 1,
      rr_ratio: 2,
      candles: [],
    });

    setResult(res);
  };

  return (
    <div>
      <h3>Run Strategy</h3>

      <select onChange={(e) => setSelected(e.target.value)}>
        <option>Select</option>
        {strategies.map((s) => (
          <option key={s}>{s}</option>
        ))}
      </select>

      <button onClick={run}>Run</button>

      <pre>{JSON.stringify(result, null, 2)}</pre>
    </div>
  );
}