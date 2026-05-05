import { useState } from "react";
import { api } from "../services/api";

export default function ExecutionForm() {
  const [result, setResult] = useState<any>(null);

  const submit = async () => {
    const res = await api.execution({
      mode: "PAPER",
      account_id: "paper-default",
      signal: {
        strategy_name: "breakout",
        symbol: "NIFTY",
        side: "BUY",
        entry_price: "100",
        stop_loss: "99",
        target_price: "102",
        quantity: "1",
      },
    });

    setResult(res);
  };

  return (
    <div>
      <h3>Execution</h3>
      <button onClick={submit}>Execute Trade</button>

      <pre>{JSON.stringify(result, null, 2)}</pre>
    </div>
  );
}