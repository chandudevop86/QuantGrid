import { useEffect, useState } from "react";
import { api } from "../api/dashboard";

export default function Dashboard() {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    api.summary().then(setData);
  }, []);

  if (!data) return <div>Loading...</div>;

  return (
    <div className="grid grid-cols-4 gap-4">
      <div className="bg-gray-900 p-4 rounded">Broker: {data.broker}</div>
      <div className="bg-gray-900 p-4 rounded">Trades: {data.trades}</div>
      <div className="bg-gray-900 p-4 rounded">Signals: {data.signals}</div>
      <div className="bg-gray-900 p-4 rounded">Status: {data.status}</div>
    </div>
  );
}