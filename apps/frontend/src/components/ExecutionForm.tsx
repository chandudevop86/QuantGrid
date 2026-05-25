import { useState } from "react";
import { api } from "../services/api";

export default function ExecutionForm() {
  const [result, setResult] = useState<any>(null);
  const [signal, setSignal] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const entry = signal?.entry_price ?? signal?.entry ?? "Signal";
  const stop = signal?.stop_loss ?? signal?.stop ?? "Signal";
  const target = signal?.target_price ?? signal?.target ?? "Signal";

  const demoSignal = {
    strategy_name: "demo",
    symbol: "NIFTY",
    side: "BUY",
    entry_price: 22500,
    stop_loss: 22450,
    target_price: 22600,
    signal_time: new Date().toISOString(),
    metadata: {
      quantity: 1,
      mode: "PAPER",
      account_id: "paper-demo",
    },
  };

  const submit = async () => {
    try {
      setLoading(true);
      setError(null);
      setResult(null);
      setSignal(null);

      const res = await api.executeAutoPaper({
        symbol: "NIFTY",
        interval: "1m",
        period: "1d",
        capital: 100000,
        risk_pct: 1,
        rr_ratio: 2,
      });
      setSignal(res?.order ?? res);
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

  const submitDemo = async () => {
    try {
      setLoading(true);
      setError(null);
      setResult(null);
      setSignal(demoSignal);

      const res = await api.executeOrder(demoSignal);
      setResult({
        ...res,
        strategy_checked: "demo",
        signal: demoSignal,
        note: "Demo signal for paper execution testing only.",
      });
    } catch (err: any) {
      const message =
        err?.response?.data?.detail ??
        err?.message ??
        "Demo execution failed";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="form-panel execution-panel">
      <div className="form-panel-header">
        <div>
          <h2>Paper Order</h2>
          <p>Auto-scan NIFTY strategies and submit the first validated paper order.</p>
        </div>
        <span className="environment-badge">{signal?.side ?? "AUTO"}</span>
      </div>

      <div className="order-summary">
        <span>
          <strong>NIFTY</strong>
          Symbol
        </span>
        <span>
          <strong>{entry}</strong>
          Entry
        </span>
        <span>
          <strong>{stop}</strong>
          Stop
        </span>
        <span>
          <strong>{target}</strong>
          Target
        </span>
      </div>

      <button
        onClick={submit}
        disabled={loading}
        className="primary-action"
      >
        {loading ? "Scanning..." : "Auto Execute Trade"}
      </button>

      <button
        type="button"
        onClick={submitDemo}
        disabled={loading}
        className="refresh-button"
      >
        Demo Paper Signal
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
