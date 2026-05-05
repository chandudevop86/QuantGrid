import { useState } from "react";
import { api } from "../api/dashboard";

export default function LiveAnalysis() {
  const [result, setResult] = useState<any>(null);

  const run = async () => {
    const res = await api.runAnalysis({
      symbol: "NIFTY",
      interval: "1m",
      period: "1d",
      strategy: "breakout",
      capital: 100000,
      risk_pct: 1,
      rr_ratio: 2,
    });

    setResult(res);
  };

  return (
    <div>
      <button
        onClick={run}
        className="bg-blue-500 px-4 py-2 rounded"
      >
        Run Analysis
      </button>

      <pre className="mt-4 bg-gray-900 p-4">
        {JSON.stringify(result, null, 2)}
      </pre>
    </div>
  );
}