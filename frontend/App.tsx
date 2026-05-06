import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";

import Dashboard from "./pages/dashboard/Dashboard";
import LiveAnalysis from "./pages/analysis/LiveAnalysis";
import Jobs from "./pages/jobs/Jobs";

/* =======================
   LAYOUT
======================= */
function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen bg-gray-950 text-white">

      {/* Sidebar */}
      <div className="w-64 bg-gray-900 p-5 border-r border-gray-800">
        <h2 className="text-2xl font-bold mb-8">🚀 QuantGrid</h2>

        <nav className="space-y-4">
          <NavLink to="/" className="hover:text-blue-400">Dashboard</NavLink>
          <NavLink to="/analysis" className="hover:text-blue-400">Analysis</NavLink>
          <NavLink to="/jobs" className="hover:text-blue-400">Jobs</NavLink>
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
   APP ROOT
======================= */
export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/analysis" element={<LiveAnalysis />} />
          <Route path="/jobs" element={<Jobs />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}