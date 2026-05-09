import { api } from "../api";

export default function Trade() {
  const placeOrder = async () => {
    try {
      const result = await api.executeOrder({
        symbol: "BTCUSDT",
        side: "BUY",
        qty: 1,
      });

      console.log(result);
    } catch (err) {
      console.error("Order failed:", err);
    }
  };

  return (
    <div>
      <h1>Trade</h1>
      <button onClick={placeOrder}>Buy</button>
    </div>
  );
}