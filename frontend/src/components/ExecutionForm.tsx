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
      const message =
        err?.response?.data?.detail ??
        err?.message ??
        "Execution failed";
      setError(
        message === "Network Error"
          ? "Cannot reach the trading API. Check that the backend is running on port 8000 and that the port is open."
          : message
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="form-panel execution-panel">
      <div className="form-panel-header">
        <div>
          <h2>Paper Order</h2>
          <p>NIFTY breakout signal with a simulated buy-side order.</p>
        </div>
        <span className="environment-badge">BUY</span>
      </div>

      <div className="order-summary">
        <span>
          <strong>NIFTY</strong>
          Symbol
        </span>
        <span>
          <strong>100</strong>
          Entry
        </span>
        <span>
          <strong>99</strong>
          Stop
        </span>
        <span>
          <strong>102</strong>
          Target
        </span>
      </div>

      <button
        onClick={submit}
        disabled={loading}
        className="primary-action"
      >
        {loading ? "Executing..." : "Execute Trade"}
      </button>

      {error && (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      )}

      {result && (
        <pre>
          {JSON.stringify(result, null, 2)}
        </pre>
      )}
    </div>
  );
}
