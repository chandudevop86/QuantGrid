import { useState } from "react";
import { api } from "../services/api";

const strategies = [
  "amd",
  "breakout",
  "btst",
  "mean_reversion",
  "mtf",
  "supply_demand",
];

export default function ExecutionForm() {
  const [result, setResult] = useState<any>(null);
  const [signal, setSignal] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

      const candleData = await api.candles("NIFTY", "1m");
      const candles = Array.isArray(candleData?.candles) ? candleData.candles : [];
      let selectedSignal: any = null;
      let selectedStrategy: string | null = null;

      for (const strategy of strategies) {
        const signals = await api.runSignals({
          strategy_name: strategy,
          symbol: "NIFTY",
          capital: 100000,
          risk_pct: 1,
          rr_ratio: 2,
          candle_source: candleData?.source,
          candles,
        });

        if (Array.isArray(signals) && signals.length > 0) {
          selectedSignal = signals[0];
          selectedStrategy = strategy;
          break;
        }
      }

      if (!selectedSignal) {
        setResult({
          status: "no_trade",
          source: "signal_based",
          reason: "No validated signal found across auto-scan strategies.",
          candles_analyzed: candles.length,
          strategies_checked: strategies,
        });
        return;
      }

      setSignal(selectedSignal);
      const res = await api.executeOrder(selectedSignal);

      setResult({
        ...res,
        strategy_checked: selectedStrategy,
        signal: selectedSignal,
      });
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
          <strong>{signal ? signal.entry_price : "Signal"}</strong>
          Entry
        </span>
        <span>
          <strong>{signal ? signal.stop_loss : "Signal"}</strong>
          Stop
        </span>
        <span>
          <strong>{signal ? signal.target_price : "Signal"}</strong>
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
