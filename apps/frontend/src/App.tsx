import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import AppLayout from "./layouts/AppLayout";
import AdminNotifications from "./pages/AdminNotifications";
import AdminUsers from "./pages/AdminUsers";
import Candles from "./pages/Candles";
import Dashboard from "./pages/Dashboard";
import Execution from "./pages/Execution";
import LiveAnalysis from "./pages/LiveAnalysis";
import Jobs from "./pages/Jobs";
import OptionChain from "./pages/OptionChain";
import Operations from "./pages/Operations";
import ProfessionalSignals from "./pages/ProfessionalSignals";
import Strategies from "./pages/Strategies";
import Trade from "./pages/Trade";
import RequireRole from "./components/RequireRole";

function protect(path: string, page: React.ReactNode) {
  return <RequireRole path={path}>{page}</RequireRole>;
}

export default function App() {
  return (
    <BrowserRouter>
      <AppLayout>
        <Routes>
          <Route path="/" element={protect("/", <Dashboard />)} />
          <Route path="/candles" element={protect("/candles", <Candles />)} />
          <Route path="/execution" element={protect("/execution", <Execution />)} />
          <Route path="/live" element={protect("/live", <LiveAnalysis />)} />
          <Route path="/analysis" element={protect("/analysis", <LiveAnalysis />)} />
          <Route path="/option-chain" element={protect("/option-chain", <OptionChain />)} />
          <Route path="/jobs" element={protect("/jobs", <Jobs />)} />
          <Route path="/operations" element={protect("/operations", <Operations />)} />
          <Route path="/signals" element={protect("/signals", <ProfessionalSignals />)} />
          <Route path="/strategies" element={protect("/strategies", <Strategies />)} />
          <Route path="/trade" element={protect("/trade", <Trade />)} />
          <Route path="/admin/users" element={protect("/admin/users", <AdminUsers />)} />
          <Route path="/admin/notifications" element={protect("/admin/notifications", <AdminNotifications />)} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppLayout>
    </BrowserRouter>
  );
}
