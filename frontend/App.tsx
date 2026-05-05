import { useEffect, useState } from "react";
import axios from "axios";

export default function App() {
  const [strategies, setStrategies] = useState<string[]>([]);
  const [selected, setSelected] = useState("");
  const [signals, setSignals] = useState<any[]>([]);

  useEffect(() => {
    axios.get("http://13.222.179.171:8000/trading/strategies")
      .then(res => setStrategies(res.data));
  }, []);

  const runStrategy = async () => {
    const res = await axios.post("http://13.222.179.171:8000/trading/signals", {
      strategy_name: selected,
      symbol: "NIFTY",
      capital: 100000,
      risk_pct: 1,
      rr_ratio: 2,
      candles: [] // later connect real data
    });

    setSignals(res.data);
  };

  return (
    <div className="flex h-screen bg-gray-950 text-white">

      {/* Sidebar */}
      <div className="w-60 bg-gray-900 p-4">
        <h2 className="text-xl font-bold mb-6">🚀 QuantGrid</h2>
        <ul className="space-y-3">
          <li className="hover:text-blue-400 cursor-pointer">Dashboard</li>
          <li className="hover:text-blue-400 cursor-pointer">Strategies</li>
          <li className="hover:text-blue-400 cursor-pointer">Orders</li>
          <li className="hover:text-blue-400 cursor-pointer">Positions</li>
        </ul>
      </div>

      {/* Main */}
      <div className="flex-1 flex flex-col">

        {/* Topbar */}
        <div className="h-14 bg-gray-900 flex items-center justify-between px-6 border-b border-gray-800">
          <h1 className="text-lg font-semibold">Trading Dashboard</h1>

          <div className="flex gap-4">
            <select
              className="bg-gray-800 p-2 rounded"
              onChange={(e) => setSelected(e.target.value)}
            >
              <option>Select Strategy</option>
              {strategies.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>

            <button
              onClick={runStrategy}
              className="bg-blue-600 px-4 py-2 rounded hover:bg-blue-500"
            >
              Run
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 grid grid-rows-2 gap-4 p-4">

          {/* Chart */}
          <div className="bg-gray-900 rounded p-4">
            <h3 className="mb-2">Chart</h3>

            {/* TradingView Embed */}
            <iframe
              src="https://s.tradingview.com/widgetembed/?symbol=NSE:NIFTY&interval=5&theme=dark"
              width="100%"
              height="300"
            />
          </div>

          {/* Signals Table */}
          <div className="bg-gray-900 rounded p-4 overflow-auto">
            <h3 className="mb-2">Signals</h3>

            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-gray-700">
                  <th>Type</th>
                  <th>Entry</th>
                  <th>SL</th>
                  <th>Target</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((s, i) => (
                  <tr key={i} className="border-b border-gray-800">
                    <td className={s.type === "BUY" ? "text-green-400" : "text-red-400"}>
                      {s.type}
                    </td>
                    <td>{s.entry}</td>
                    <td>{s.stop_loss}</td>
                    <td>{s.target}</td>
                  </tr>
                ))}
              </tbody>
            </table>

          </div>
        </div>
      </div>
    </div>
  );
}