import { useState } from "react";
import { api } from "../api";

export default function Trade() {
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const placeOrder = async () => {
    try {
      setLoading(true);
      setError(null);
      setResult(null);

      const response = await api.executeOrder({
        strategy_name: "manual",
        symbol: "NIFTY",
        side: "BUY",
        entry_price: 22450,
        stop_loss: 22410,
        target_price: 22530,
        signal_time: new Date().toISOString(),
        metadata: {
          quantity: 1,
          mode: "PAPER",
          account_id: "paper-default",
        },
      });

      setResult(response);
    } catch (err: any) {
      const message =
        err?.response?.data?.detail ??
        err?.message ??
        "Order failed";
      setError(
        message === "Network Error"
          ? "Cannot reach the trading API. Check that the backend is running on port 8000."
          : message
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="dashboard-page">
      <div className="page-heading">
        <h1>Trade</h1>
        <p>Place a manual paper trade through the execution API.</p>
      </div>

      <div className="form-panel execution-panel">
        <div className="form-panel-header">
          <div>
            <h2>Manual Paper Order</h2>
            <p>NIFTY buy order routed to the same execution endpoint.</p>
          </div>
          <span className="environment-badge">BUY</span>
        </div>

        <div className="order-summary">
          <span>
            <strong>NIFTY</strong>
            Symbol
          </span>
          <span>
            <strong>22450</strong>
            Entry
          </span>
          <span>
            <strong>22410</strong>
            Stop
          </span>
          <span>
            <strong>22530</strong>
            Target
          </span>
        </div>

        <button
          type="button"
          onClick={placeOrder}
          disabled={loading}
          className="primary-action"
        >
          {loading ? "Placing Order..." : "Buy Paper Lot"}
        </button>

        {error && (
          <div className="alert alert-error" role="alert">
            {error}
          </div>
        )}

        {result && (
          <>
            <div className="alert alert-success" role="status">
              Paper order accepted.
            </div>
            <pre>{JSON.stringify(result, null, 2)}</pre>
          </>
        )}
      </div>
    </section>
  );
}
