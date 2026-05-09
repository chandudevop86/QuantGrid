import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import LiveAnalysis from "./pages/LiveAnalysis";
import Jobs from "./pages/Jobs";

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen bg-gray-950 text-white">

      {/* Sidebar */}
     <nav className="space-y-4">
  <NavLink
    to="/"
    className={({ isActive }) =>
      `block ${isActive ? "text-blue-400 font-semibold" : "hover:text-blue-400"}`
    }
  >
    Dashboard
  </NavLink>

  <NavLink
    to="/analysis"
    className={({ isActive }) =>
      `block ${isActive ? "text-blue-400 font-semibold" : "hover:text-blue-400"}`
    }
  >
    Live Analysis
  </NavLink>

  <NavLink
    to="/jobs"
    className={({ isActive }) =>
      `block ${isActive ? "text-blue-400 font-semibold" : "hover:text-blue-400"}`
    }
  >
    Jobs
  </NavLink>
</nav>

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
