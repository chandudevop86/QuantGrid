import { Navigate, Route, Routes } from "react-router-dom";

import Candles from "./src/pages/Candles";
import Dashboard from "./src/pages/Dashboard";
import Execution from "./src/pages/Execution";
import Jobs from "./src/pages/Jobs";
import LiveAnalysis from "./src/pages/LiveAnalysis";
import Strategies from "./src/pages/Strategies";
import Trade from "./src/pages/Trade";

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/candles" element={<Candles />} />
      <Route path="/execution" element={<Execution />} />
      <Route path="/live" element={<LiveAnalysis />} />
      <Route path="/analysis" element={<LiveAnalysis />} />
      <Route path="/jobs" element={<Jobs />} />
      <Route path="/strategies" element={<Strategies />} />
      <Route path="/trade" element={<Trade />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
