import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useUiMode } from "../hooks/useUiMode";

type TradeSide = "BUY" | "SELL";

export default function Trade() {
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [priceLoading, setPriceLoading] = useState(true);
  const [marketPrice, setMarketPrice] = useState<number | null>(null);
  const [marketSource, setMarketSource] = useState<string | null>(null);
  const [side, setSide] = useState<TradeSide>("BUY");
  const developerMode = useUiMode() === "developer";

  const order = useMemo(() => {
    const entry = marketPrice ?? 0;
    const stopDistance = Math.max(25, entry * 0.0015);
    const targetDistance = stopDistance * 2;

    return {
      symbol: "NIFTY",
      entry: Number(entry.toFixed(2)),
      stop: Number((side === "BUY" ? entry - stopDistance : entry + stopDistance).toFixed(2)),
      target: Number((side === "BUY" ? entry + targetDistance : entry - targetDistance).toFixed(2)),
    };
  }, [marketPrice, side]);

  const loadPrice = async () => {
    try {
      setPriceLoading(true);
      setError(null);

      const priceData = await api.getPrice();
      const price = Number(priceData?.price);
      if (!Number.isFinite(price) || price <= 0) {
        throw new Error("Live NIFTY price is unavailable.");
      }

      setMarketPrice(price);
      setMarketSource(priceData?.source ?? "Market API");
    } catch (err: any) {
      const message =
        err?.response?.data?.detail ??
        err?.message ??
        "Failed to load market price.";
      setError(
        message === "Network Error"
          ? "Cannot reach the trading API. Check that the backend is running on port 8000."
          : message
      );
    } finally {
      setPriceLoading(false);
    }
  };

  useEffect(() => {
    void loadPrice();
  }, []);

  const placeOrder = async () => {
    try {
      setLoading(true);
      setError(null);
      setResult(null);

      if (!marketPrice || marketPrice <= 0) {
        await loadPrice();
      }

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
            <p>{priceLoading ? "Loading live NIFTY price..." : `Live price from ${marketSource ?? "Market API"}`}</p>
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
          disabled={loading || priceLoading || !marketPrice}
          className="primary-action"
        >
          {loading ? "Placing Order..." : `${side === "BUY" ? "Buy" : "Sell"} Paper Lot`}
        </button>

        <button
          type="button"
          onClick={() => void loadPrice()}
          disabled={loading || priceLoading}
          className="refresh-button"
        >
          Refresh Price
        </button>

        {error && (
          <div className="alert alert-error" role="alert">
            {error}
          </div>
        )}

        {result && (
          <>
            <div className="alert alert-success" role="status">
              Paper order accepted. Risk and validation gates stayed active.
            </div>
            {developerMode && (
              <details className="technical-details" open>
                <summary>Execution API Payload</summary>
                <pre>{JSON.stringify(result, null, 2)}</pre>
              </details>
            )}
          </>
        )}
      </div>
    </section>
  );
}
