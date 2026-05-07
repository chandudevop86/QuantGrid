import { NavLink } from "react-router-dom";

export default function Sidebar() {
  return (
    <div className="w-64 bg-gray-900 p-4 border-r border-gray-800">
      <h1 className="text-xl font-bold mb-6">⚡ QuantEdge</h1>

      <div className="space-y-3">
        <NavLink to="/" className="block hover:text-blue-400">
          Dashboard
        </NavLink>
        <NavLink to="/candles" className="block hover:text-blue-400">
          Candles
        </NavLink>
        <NavLink to="/jobs" className="block hover:text-blue-400">
          Jobs
        </NavLink>
        <NavLink to="/live" className="block hover:text-blue-400">
          Live Analysis
        </NavLink>
      </div>
    </div>
  );
}