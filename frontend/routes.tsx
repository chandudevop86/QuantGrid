import { Navigate, Route, Routes } from "react-router-dom";

import Candles from "./src/pages/Candles";
import Dashboard from "./src/pages/Dashboard";
import Execution from "./src/pages/Execution";
import Jobs from "./src/pages/Jobs";
import LiveAnalysis from "./src/pages/LiveAnalysis";
import Strategies from "./src/pages/Strategies";
import Trade from "./src/pages/Trade";
import RequireRole from "./src/components/RequireRole";

function protect(path: string, page: React.ReactNode) {
  return <RequireRole path={path}>{page}</RequireRole>;
}

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={protect("/", <Dashboard />)} />
      <Route path="/candles" element={protect("/candles", <Candles />)} />
      <Route path="/execution" element={protect("/execution", <Execution />)} />
      <Route path="/live" element={protect("/live", <LiveAnalysis />)} />
      <Route path="/analysis" element={protect("/analysis", <LiveAnalysis />)} />
      <Route path="/jobs" element={protect("/jobs", <Jobs />)} />
      <Route path="/strategies" element={protect("/strategies", <Strategies />)} />
      <Route path="/trade" element={protect("/trade", <Trade />)} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
