import { useEffect, useState } from "react";
import { api } from "../api/dashboard";

export default function Candles() {
  const [data, setData] = useState<any>([]);

  useEffect(() => {
    api.candles("NIFTY").then(setData);
  }, []);

  return (
    <div>
      <h2 className="text-xl mb-4">Market Candles</h2>

      <pre className="bg-gray-900 p-4 rounded overflow-auto h-[500px]">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}