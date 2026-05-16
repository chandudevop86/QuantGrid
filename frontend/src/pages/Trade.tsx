import { useState } from "react";
import { api } from "../api";

type TradeSide = "BUY" | "SELL";

export default function Trade() {
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [side, setSide] = useState<TradeSide>("BUY");

  const order = {
    symbol: "NIFTY",
    entry: 22450,
    stop: side === "BUY" ? 22410 : 22490,
    target: side === "BUY" ? 22530 : 22370,
  };

  const placeOrder = async () => {
    try {
      setLoading(true);
      setError(null);
      setResult(null);

      const response = await api.executeOrder({
        strategy_name: "manual",
        symbol: order.symbol,
        side,
        entry_price: order.entry,
        stop_loss: order.stop,
        target_price: order.target,
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
            <p>NIFTY {side.toLowerCase()} order routed to the same execution endpoint.</p>
          </div>
          <span className="environment-badge">{side}</span>
        </div>

        <div className="side-selector" role="group" aria-label="Order side">
          <button
            type="button"
            onClick={() => setSide("BUY")}
            className={side === "BUY" ? "active" : ""}
          >
            Buy
          </button>
          <button
            type="button"
            onClick={() => setSide("SELL")}
            className={side === "SELL" ? "active danger" : "danger"}
          >
            Sell
          </button>
        </div>

        <div className="order-summary">
          <span>
            <strong>{order.symbol}</strong>
            Symbol
          </span>
          <span>
            <strong>{order.entry}</strong>
            Entry
          </span>
          <span>
            <strong>{order.stop}</strong>
            Stop
          </span>
          <span>
            <strong>{order.target}</strong>
            Target
          </span>
        </div>

        <button
          type="button"
          onClick={placeOrder}
          disabled={loading}
          className="primary-action"
        >
          {loading ? "Placing Order..." : `${side === "BUY" ? "Buy" : "Sell"} Paper Lot`}
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
