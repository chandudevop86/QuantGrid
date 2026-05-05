import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";

import Dashboard from "./pages/Dashboard";
import StrategyForm from "./components/StrategyForm";
import ExecutionForm from "./components/ExecutionForm";

function Layout({ children }) {
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

      {/* Main Area */}
      <div className="flex-1 flex flex-col">

        {/* Topbar */}
        <div className="h-14 bg-gray-900 flex items-center justify-between px-6 border-b border-gray-800">
          <h1 className="text-lg font-semibold">Trading Dashboard</h1>
        </div>

        {/* Page Content */}
        <div className="p-6 overflow-auto">
          {children}
        </div>

      </div>
    </div>
  );
}

function DashboardPage() {
  return (
    <div className="bg-gray-900 p-4 rounded-xl shadow">
      <Dashboard />
    </div>
  );
}

function StrategyPage() {
  return (
    <div className="bg-gray-900 p-4 rounded-xl shadow">
      <StrategyForm />
    </div>
  );
}

function ExecutionPage() {
  return (
    <div className="bg-gray-900 p-4 rounded-xl shadow">
      <ExecutionForm />
    </div>
  );
}

function App() {
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

export default App;