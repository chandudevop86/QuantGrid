import { useState } from "react";
import { api } from "../services/api";

export default function ExecutionForm() {
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    try {
      setLoading(true);
      setError(null);

      const res = await api.executeOrder({
        strategy_name: "breakout",
        symbol: "NIFTY",
        side: "BUY",
        entry_price: 100,
        stop_loss: 99,
        target_price: 102,
        signal_time: new Date().toISOString(),
        metadata: {
          quantity: 1,
          mode: "PAPER",
          account_id: "paper-default",
        },
      });

      setResult(res);
    } catch (err: any) {
      setError(err.message || "Execution failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-gray-900 p-4 rounded-xl">

      <h3 className="text-lg font-semibold mb-3">Execution</h3>

      {/* Execute Button */}
      <button
        onClick={submit}
        disabled={loading}
        className="bg-green-600 hover:bg-green-700 px-4 py-2 rounded w-full"
      >
        {loading ? "Executing..." : "Execute Trade"}
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
