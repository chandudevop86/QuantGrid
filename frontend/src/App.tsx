import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import AppLayout from "./layouts/AppLayout";
import Candles from "./pages/Candles";
import Dashboard from "./pages/Dashboard";
import Execution from "./pages/Execution";
import LiveAnalysis from "./pages/LiveAnalysis";
import Jobs from "./pages/Jobs";
import Strategies from "./pages/Strategies";
import Trade from "./pages/Trade";

export default function App() {
  return (
    <BrowserRouter>
      <AppLayout>
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
      </AppLayout>
    </BrowserRouter>
  );
}
