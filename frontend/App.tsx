import React from "react";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";

/* =======================
   DASHBOARD PAGE (mock)
======================= */
function Dashboard() {
  return (
    <div className="bg-gray-900 p-4 rounded-xl shadow">
      <h2 className="text-xl font-semibold">Dashboard</h2>
      <p className="text-gray-400 mt-2">Market overview coming soon...</p>
    </div>
  );
}

/* =======================
   STRATEGY UI (MERGED)
======================= */
const strategies = [
  { name: "amd", desc: "Accumulation → Manipulation → Distribution" },
  { name: "breakout", desc: "Momentum breakout strategy" },
  { name: "btst", desc: "Buy Today Sell Tomorrow" },
  { name: "mean_reversion", desc: "Price returns to mean" },
  { name: "mtf", desc: "Multi-timeframe analysis" },
  { name: "supply_demand", desc: "Liquidity zones strategy" },
];

function StrategyForm() {
  return (
    <div>
      <h2 className="text-xl font-semibold mb-4">Strategies</h2>

      <div className="grid grid-cols-2 gap-3">
        {strategies.map((s) => (
          <button
            key={s.name}
            className="bg-gray-800 hover:bg-gray-700 p-3 rounded-lg text-left transition"
          >
            <div className="text-blue-400 font-semibold uppercase">
              {s.name}
            </div>
            <div className="text-xs text-gray-400">{s.desc}</div>
          </button>
        ))}
      </div>
    </div>
  );
}

/* =======================
   EXECUTION PAGE (mock)
======================= */
function ExecutionForm() {
  return (
    <div className="bg-gray-900 p-4 rounded-xl shadow">
      <h2 className="text-xl font-semibold">Execution Panel</h2>
      <p className="text-gray-400 mt-2">Order execution UI coming soon...</p>
    </div>
  );
}

/* =======================
   LAYOUT
======================= */
type LayoutProps = {
  children: React.ReactNode;
};

function Layout({ children }: LayoutProps) {
  return (
    <div className="flex h-screen bg-gray-950 text-white">

      {/* Sidebar */}
      <div className="w-64 bg-gray-900 p-5 border-r border-gray-800">
        <h2 className="text-2xl font-bold mb-8">🚀 QuantGrid</h2>

        <nav className="space-y-4">
          <NavLink
            to="/"
            className={({ isActive }) =>
              isActive ? "text-blue-400 font-semibold" : "hover:text-blue-400"
            }
          >
            Dashboard
          </NavLink>

          <NavLink
            to="/strategies"
            className={({ isActive }) =>
              isActive ? "text-blue-400 font-semibold" : "hover:text-blue-400"
            }
          >
            Strategies
          </NavLink>

          <NavLink
            to="/execution"
            className={({ isActive }) =>
              isActive ? "text-blue-400 font-semibold" : "hover:text-blue-400"
            }
          >
            Execution
          </NavLink>
        </nav>
      </div>

      {/* Main */}
      <div className="flex-1 flex flex-col">

        <div className="h-14 bg-gray-900 flex items-center px-6 border-b border-gray-800">
          <h1 className="text-lg font-semibold">Trading Dashboard</h1>
        </div>

        <div className="p-6 overflow-auto">
          {children}
        </div>

      </div>
    </div>
  );
}

/* =======================
   PAGES
======================= */
const DashboardPage = () => <Dashboard />;
const StrategyPage = () => <StrategyForm />;
const ExecutionPage = () => <ExecutionForm />;

/* =======================
   APP ROOT
======================= */
export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/strategies" element={<StrategyPage />} />
          <Route path="/execution" element={<ExecutionPage />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}



import { BrowserRouter, Routes, Route } from "react-router-dom";

import Dashboard from "./pages/dashboard/Dashboard";
import LiveAnalysis from "./pages/analysis/LiveAnalysis";
import Jobs from "./pages/jobs/Jobs";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/analysis" element={<LiveAnalysis />} />
        <Route path="/jobs" element={<Jobs />} />
      </Routes>
    </BrowserRouter>
  );
}