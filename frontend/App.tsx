import React from "react";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";

import Dashboard from "./pages/Dashboard";
import StrategyForm from "./components/StrategyForm";
import ExecutionForm from "./components/ExecutionForm";

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

const DashboardPage = () => (
  <div className="bg-gray-900 p-4 rounded-xl shadow">
    <Dashboard />
  </div>
);

const StrategyPage = () => (
  <div className="bg-gray-900 p-4 rounded-xl shadow">
    <StrategyForm />
  </div>
);

const ExecutionPage = () => (
  <div className="bg-gray-900 p-4 rounded-xl shadow">
    <ExecutionForm />
  </div>
);

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