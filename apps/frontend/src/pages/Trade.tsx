import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { useUiMode } from "../hooks/useUiMode";
import { getCurrentMode, type TradingMode } from "../mode";

type TradeSide = "BUY" | "SELL";
type TslMode = "percent" | "price";
type OrderDraft = {
  symbol: string;
  side: TradeSide;
  entry: number;
  stop: number;
  target: number;
  quantity: number;
  roundedQuantity: number;
  trailingStopLoss: number | null;
  trailingStopPct: number | null;
};

const numberInput = (value: number) => (Number.isFinite(value) && value > 0 ? String(value) : "");
const formatNumberForTrade = (value: number) => Number.isFinite(value) && value > 0
  ? value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  : "—";
const parsedPositive = (value: string) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
};
const lotSizeForSymbol = (symbol: string) => (symbol === "NIFTY" ? 65 : 1);
const roundDownToLot = (quantity: number | null, lotSize: number) => {
  if (!quantity || quantity <= 0) return 0;
  return Math.floor(quantity / lotSize) * lotSize;
};

export default function Trade() {
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [priceLoading, setPriceLoading] = useState(true);
  const [marketPrice, setMarketPrice] = useState<number | null>(null);
  const [marketSource, setMarketSource] = useState<string | null>(null);
  const [side, setSide] = useState<TradeSide>("BUY");
  const [stopLossInput, setStopLossInput] = useState("");
  const [targetInput, setTargetInput] = useState("");
  const [tslEnabled, setTslEnabled] = useState(true);
  const [tslMode, setTslMode] = useState<TslMode>("percent");
  const [trailingStopInput, setTrailingStopInput] = useState("");
  const [trailingPctInput, setTrailingPctInput] = useState("0.5");
  const [quantityInput, setQuantityInput] = useState("65");
  const [mode, setMode] = useState<TradingMode>(getCurrentMode());
  const [brokerStatus, setBrokerStatus] = useState<any>(null);
  const [pendingLiveOrder, setPendingLiveOrder] = useState<OrderDraft | null>(null);
  const developerMode = useUiMode() === "developer";
  const isLive = mode === "live";
  const readiness = brokerStatus?.live_readiness;
  const liveReady = Boolean(readiness?.live_ready && brokerStatus?.connected);

  const defaults = useMemo(() => {
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

  useEffect(() => {
    setStopLossInput(numberInput(defaults.stop));
    setTargetInput(numberInput(defaults.target));
    setTrailingStopInput(numberInput(defaults.stop));
  }, [defaults.stop, defaults.target]);

  const order = useMemo(() => {
    return {
      ...defaults,
      stop: parsedPositive(stopLossInput) ?? defaults.stop,
      target: parsedPositive(targetInput) ?? defaults.target,
    };
  }, [defaults, stopLossInput, targetInput]);
  const requestedQuantity = parsedPositive(quantityInput);
  const lotSize = lotSizeForSymbol(order.symbol);
  const roundedQuantity = roundDownToLot(requestedQuantity, lotSize);
  const lots = roundedQuantity > 0 ? roundedQuantity / lotSize : 0;
  const adjustLots = (delta: number) => {
    const nextLots = Math.max(1, lots + delta || 1);
    setQuantityInput(String(nextLots * lotSize));
  };

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

  useEffect(() => {
    api.brokerStatus().then(setBrokerStatus).catch(() => setBrokerStatus(null));
  }, [mode]);

  useEffect(() => {
    const syncMode = () => setMode(getCurrentMode());
    window.addEventListener("quantgrid-mode-change", syncMode);
    window.addEventListener("storage", syncMode);
    return () => {
      window.removeEventListener("quantgrid-mode-change", syncMode);
      window.removeEventListener("storage", syncMode);
    };
  }, []);

  const buildOrderDraft = async (): Promise<OrderDraft> => {
    if (!marketPrice || marketPrice <= 0) {
      await loadPrice();
    }

    const trailingStopLoss = tslEnabled && tslMode === "price" ? parsedPositive(trailingStopInput) : null;
    const trailingStopPct = tslEnabled && tslMode === "percent" ? parsedPositive(trailingPctInput) : null;
    const quantity = parsedPositive(quantityInput);
    const draftLotSize = lotSizeForSymbol(order.symbol);
    const draftRoundedQuantity = roundDownToLot(quantity, draftLotSize);

    if (side === "BUY" && !(order.stop < order.entry && order.entry < order.target)) {
      throw new Error("BUY order requires Stop < Entry < Target.");
    }
    if (side === "SELL" && !(order.target < order.entry && order.entry < order.stop)) {
      throw new Error("SELL order requires Target < Entry < Stop.");
    }
    if (tslEnabled && tslMode === "percent" && !trailingStopPct) {
      throw new Error("Trailing stop percent must be greater than 0.");
    }
    if (tslEnabled && tslMode === "price" && !trailingStopLoss) {
      throw new Error("Trailing stop price must be greater than 0.");
    }
    if (trailingStopLoss && side === "BUY" && trailingStopLoss >= order.entry) {
      throw new Error("BUY trailing stop price must be below entry.");
    }
    if (trailingStopLoss && side === "SELL" && trailingStopLoss <= order.entry) {
      throw new Error("SELL trailing stop price must be above entry.");
    }
    if (!quantity || !Number.isInteger(quantity)) {
      throw new Error("Quantity must be a whole number greater than 0.");
    }
    if (draftRoundedQuantity <= 0) {
      throw new Error(`Quantity must be at least one ${draftLotSize} lot.`);
    }
    if (quantity !== draftRoundedQuantity) {
      throw new Error(`Quantity will round down to ${draftRoundedQuantity}. Enter a multiple of ${draftLotSize} before submit.`);
    }
    if (isLive && !liveReady) {
      throw new Error("Live readiness checks are not passing. Review the readiness panel before placing a live order.");
    }

    return {
      symbol: order.symbol,
      side,
      entry: order.entry,
      stop: order.stop,
      target: order.target,
      quantity,
      roundedQuantity: draftRoundedQuantity,
      trailingStopLoss,
      trailingStopPct,
    };
  };

  const submitOrder = async (draft: OrderDraft) => {
    try {
      setLoading(true);
      setError(null);
      setResult(null);
      const response = await api.executeOrder({
        strategy_name: "manual",
        symbol: draft.symbol,
        side: draft.side,
        entry_price: draft.entry,
        stop_loss: draft.stop,
        target_price: draft.target,
        trailing_stop_loss: draft.trailingStopLoss,
        trailing_stop_pct: draft.trailingStopPct,
        signal_time: new Date().toISOString(),
        metadata: {
          quantity: draft.roundedQuantity,
          mode: isLive ? "LIVE" : "PAPER",
          account_id: isLive ? "live-default" : "paper-default",
          trailing_stop_enabled: tslEnabled,
          trailing_stop_mode: tslEnabled ? tslMode : "off",
        },
      });

      setResult(response);
      setPendingLiveOrder(null);
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

  const placeOrder = async () => {
    try {
      setError(null);
      setResult(null);
      const draft = await buildOrderDraft();
      if (isLive) {
        setPendingLiveOrder(draft);
        return;
      }
      await submitOrder(draft);
    } catch (err: any) {
      setError(err?.message ?? "Order failed");
    }
  };

  return (
    <section className="dashboard-page trade-page">
      <div className="page-heading trade-heading">
        <div><span className="page-eyebrow">Order ticket</span><h1>{isLive ? "Live Order" : "Paper Order"}</h1></div>
        <p>{isLive ? "Review and confirm a broker order." : "Test the setup without risking real money."}</p>
      </div>

      <div className="form-panel execution-panel trade-ticket">
        <div className="form-panel-header">
          <div>
            <span className="metric-label">NIFTY 50 · 1 lot = 65</span>
            <h2>{priceLoading ? "Loading price…" : formatNumberForTrade(order.entry)}</h2>
            <p>{marketSource ?? "Market API"}</p>
          </div>
          <span className="environment-badge">{mode.toUpperCase()} {side}</span>
        </div>

        {isLive && (
          <div className={liveReady ? "alert alert-success" : "alert alert-error live-warning"} role="alert">
            {liveReady
              ? "Live readiness checks are passing. Confirm order details carefully before submitting."
              : "Live mode is selected, but readiness checks are not passing."}
          </div>
        )}

        {isLive && (
          <div className="live-readiness-grid">
            <span className={brokerStatus?.live_trading_enabled ? "health-ok" : "health-fail"}>
              <strong>Live flag</strong>
              <small>{brokerStatus?.live_trading_enabled ? "Enabled" : "Disabled"}</small>
            </span>
            <span className={brokerStatus?.broker_live_enabled ? "health-ok" : "health-fail"}>
              <strong>Broker live</strong>
              <small>{brokerStatus?.broker_live_enabled ? "Enabled" : "Disabled"}</small>
            </span>
            <span className={brokerStatus?.connected ? "health-ok" : "health-fail"}>
              <strong>Broker session</strong>
              <small>{brokerStatus?.connected ? "Connected" : "Not connected"}</small>
            </span>
            <span className={brokerStatus?.risk_configured ? "health-ok" : "health-fail"}>
              <strong>Risk config</strong>
              <small>{brokerStatus?.risk_configured ? "Configured" : "Missing"}</small>
            </span>
            <span className={readiness?.stop_protection_ready ? "health-ok" : "health-fail"}>
              <strong>Stop protection</strong>
              <small>{readiness?.stop_protection_ready ? "Ready" : "Monitor not ready"}</small>
            </span>
            <span className={readiness?.exit_monitor_live_ready ? "health-ok" : "health-warn"}>
              <strong>Exit monitor</strong>
              <small>{readiness ? `${readiness.exit_monitor_mode ?? "paper"} / ${readiness.exit_monitor_interval_seconds ?? "-"}s` : "Unknown"}</small>
            </span>
          </div>
        )}

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

        <div className="order-summary trade-order-summary">
          <span>
            <strong>{order.symbol}</strong>
            Symbol
          </span>
          <span>
            <strong>{roundedQuantity || "-"}</strong>
            {lots || 0} {lots === 1 ? "lot" : "lots"}
          </span>
          <span>
            <strong>{order.stop}</strong>
            Stop
          </span>
          <span>
            <strong>{order.target}</strong>
            Target
          </span>
          <span>
            <strong>
              {tslEnabled
                ? tslMode === "percent"
                  ? `${parsedPositive(trailingPctInput) ?? "-"}%`
                  : parsedPositive(trailingStopInput) ?? "-"
                : "Off"}
            </strong>
            TSL
          </span>
        </div>

        <div className="risk-control-grid">
          <label>
            Quantity
            <div className="lot-quantity-control">
              <button type="button" onClick={() => adjustLots(-1)} aria-label="Remove one lot">−</button>
              <input type="number" inputMode="numeric" value={quantityInput} onChange={(event) => setQuantityInput(event.target.value)} min={lotSize} step={lotSize} />
              <button type="button" onClick={() => adjustLots(1)} aria-label="Add one lot">+</button>
            </div>
            <small className="input-helper">{lots || 0} {lots === 1 ? "lot" : "lots"} × {lotSize} units</small>
          </label>
          <label>
            Stop Loss
            <input
              type="number"
              inputMode="decimal"
              value={stopLossInput}
              onChange={(event) => setStopLossInput(event.target.value)}
              min="0"
              step="0.05"
            />
          </label>
          <label>
            Target
            <input
              type="number"
              inputMode="decimal"
              value={targetInput}
              onChange={(event) => setTargetInput(event.target.value)}
              min="0"
              step="0.05"
            />
          </label>
        </div>

        <div className="risk-box">
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={tslEnabled}
              onChange={(event) => setTslEnabled(event.target.checked)}
            />
            Enable trailing stop loss
          </label>
          {tslEnabled && (
            <>
              <div className="side-selector compact" role="group" aria-label="Trailing stop mode">
                <button
                  type="button"
                  onClick={() => setTslMode("percent")}
                  className={tslMode === "percent" ? "active" : ""}
                >
                  Percent TSL
                </button>
                <button
                  type="button"
                  onClick={() => setTslMode("price")}
                  className={tslMode === "price" ? "active" : ""}
                >
                  Price TSL
                </button>
              </div>
              {tslMode === "percent" ? (
                <label>
                  Trail Percent
                  <input
                    type="number"
                    inputMode="decimal"
                    value={trailingPctInput}
                    onChange={(event) => setTrailingPctInput(event.target.value)}
                    min="0.05"
                    step="0.05"
                  />
                </label>
              ) : (
                <label>
                  Trailing Stop Price
                  <input
                    type="number"
                    inputMode="decimal"
                    value={trailingStopInput}
                    onChange={(event) => setTrailingStopInput(event.target.value)}
                    min="0"
                    step="0.05"
                  />
                </label>
              )}
            </>
          )}
        </div>

        <button
          type="button"
          onClick={placeOrder}
          disabled={loading || priceLoading || !marketPrice || (isLive && !liveReady)}
          className={isLive ? "primary-action live-action" : "primary-action"}
        >
          {loading ? "Placing Order..." : `${side === "BUY" ? "Buy" : "Sell"} ${isLive ? "Live" : "Paper"} Order`}
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
              {isLive ? "Live order request accepted by the execution API." : "Paper order accepted. Risk and validation gates stayed active."}
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

      {pendingLiveOrder && (
        <div className="modal-backdrop" role="presentation">
          <div className="live-confirm-modal" role="dialog" aria-modal="true" aria-labelledby="live-confirm-title">
            <div className="modal-header">
              <div>
                <h2 id="live-confirm-title">Confirm Live Trade</h2>
                <p>This is a real money order. Review every field before submitting.</p>
              </div>
              <span className="environment-badge danger">REAL MONEY</span>
            </div>
            <div className="confirm-grid">
              <span><strong>{pendingLiveOrder.symbol}</strong>Symbol</span>
              <span><strong>{pendingLiveOrder.side}</strong>Side</span>
              <span><strong>{pendingLiveOrder.roundedQuantity}</strong>Quantity</span>
              <span><strong>{pendingLiveOrder.entry}</strong>Entry</span>
              <span><strong>{pendingLiveOrder.stop}</strong>Stop Loss</span>
              <span><strong>{pendingLiveOrder.target}</strong>Target</span>
              <span>
                <strong>
                  {pendingLiveOrder.trailingStopPct
                    ? `${pendingLiveOrder.trailingStopPct}%`
                    : pendingLiveOrder.trailingStopLoss ?? "Off"}
                </strong>
                TSL
              </span>
              <span><strong>{readiness?.exit_monitor_live_ready ? "Ready" : "Not ready"}</strong>Exit Monitor</span>
            </div>
            <div className="alert alert-error" role="alert">
              Submitting will send this order to the live broker if backend guardrails pass.
            </div>
            <div className="modal-actions">
              <button type="button" className="refresh-button" onClick={() => setPendingLiveOrder(null)} disabled={loading}>
                Cancel
              </button>
              <button type="button" className="primary-action live-action" onClick={() => void submitOrder(pendingLiveOrder)} disabled={loading}>
                {loading ? "Submitting..." : "Submit Real Money Order"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
