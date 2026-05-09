
import { useEffect, useState } from "react";
import { api } from "../api";

export default function Strategies() {
  const [strategies, setStrategies] = useState([]);

  useEffect(() => {
    api.getStrategies().then(setStrategies);
  }, []);

  const runStrategy = async (name: string) => {
    try {
      const result = await api.runSignals({
        strategy: name,
        data: [
          { open: 100, high: 105, low: 95, close: 102 },
          { open: 102, high: 108, low: 101, close: 107 }
        ]
      });

      console.log("Signal:", result);
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div>
      <h1>Strategies</h1>

      {strategies.map((s: any, i: number) => (
        <div key={i} style={{ marginBottom: "10px" }}>
          <span>{s}</span>
          <button onClick={() => runStrategy(s)}>Run</button>
        </div>
      ))}
    </div>
  );
}