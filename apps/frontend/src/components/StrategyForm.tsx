import { useEffect, useState } from "react";
import { api } from "../services/api";

export default function StrategyForm() {
  const [strategies, setStrategies] = useState<string[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.strategies()
      .then(setStrategies)
      .catch((err) => setError("Failed to load strategies"));
  }, []);

  const run = async () => {
    if (!selected) {
      setError("Please select a strategy");
      return;
    }

    try {
      setLoading(true);
      setError(null);

      const res = await api.runSignals({
        strategy_name: selected,
        symbol: "NIFTY",
        capital: 100000,
        risk_pct: 1,
        rr_ratio: 2,
        candle_source: "sample-fallback",

        candles: [
          { timestamp: new Date().toISOString(), open: 100, high: 105, low: 98, close: 103, volume: 1000 },
          { timestamp: new Date().toISOString(), open: 103, high: 108, low: 101, close: 107, volume: 1200 },
        ],
      });

      setResult(res);
    } catch (err: any) {
      setError(err.message || "Strategy execution failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-gray-900 p-4 rounded-xl">

      <h3 className="text-lg font-semibold mb-3">Run Strategy</h3>

      {/* Strategy Select */}
      <select
        className="bg-gray-800 p-2 rounded w-full mb-3"
        value={selected}
        onChange={(e) => setSelected(e.target.value)}
      >
        <option value="">Select strategy</option>

        {strategies.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>

      {/* Run Button */}
      <button
        onClick={run}
        disabled={loading}
        className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded w-full"
      >
        {loading ? "Running..." : "Run Strategy"}
      </button>

      {/* Error */}
      {error && (
        <div className="text-red-400 mt-3 text-sm">
          {error}
        </div>
      )}

      {/* Result */}
      {result && (
        <pre className="bg-black mt-4 p-3 rounded text-xs overflow-auto">
          {JSON.stringify(result, null, 2)}
        </pre>
      )}
    </div>
  );
}
