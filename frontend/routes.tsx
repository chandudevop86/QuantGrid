import { Routes, Route } from "react-router-dom";
import AppLayout from "./src/layouts/AppLayout";
import Dashboard from "./src/pages/Dashboard";
import LiveAnalysis from "./src/pages/LiveAnalysis";
import Jobs from "./src/pages/Jobs";

import AppLayout from "./layouts/AppLayout";

import Dashboard from "./pages/Dashboard";
import LiveAnalysis from "./pages/LiveAnalysis";
import Jobs from "./pages/jobs";


export default function AppRoutes() {
  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/analysis" element={<LiveAnalysis />} />
        <Route path="/jobs" element={<Jobs />} />
      </Routes>
    </AppLayout>
  );
}
}
main
