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

      const candleData = await api.candles("NIFTY", "5m");
      const signals = await api.runSignals({
        strategy_name: "breakout",
        symbol: "NIFTY",
        capital: 100000,
        risk_pct: 1,
        rr_ratio: 2,
        candles: Array.isArray(candleData?.candles) ? candleData.candles : [],
      });
      const signal = Array.isArray(signals) ? signals[0] : null;

      if (!signal) {
        setResult({ status: "no_trade", source: "signal_based" });
        return;
      }

      const res = await api.executeOrder(signal);

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
          <strong>Signal</strong>
          Entry
        </span>
        <span>
          <strong>Signal</strong>
          Stop
        </span>
        <span>
          <strong>Signal</strong>
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
