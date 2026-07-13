import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import RequireRole from "./components/RequireRole";
import LoadingSkeleton from "./components/LoadingSkeleton";
import AppLayout from "./layouts/AppLayout";
import RestrictedRoute from "./components/RestrictedRoute";

const AdminNotifications = lazy(() => import("./pages/AdminNotifications"));
const AdminUsers = lazy(() => import("./pages/AdminUsers"));
const Backtesting = lazy(() => import("./pages/Backtesting"));
const Candles = lazy(() => import("./pages/Candles"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const DhanLogin = lazy(() => import("./pages/DhanLogin"));
const Execution = lazy(() => import("./pages/Execution"));
const InstitutionalDashboard = lazy(() => import("./pages/InstitutionalDashboard"));
const Investing = lazy(() => import("./pages/Investing"));
const Jobs = lazy(() => import("./pages/Jobs"));
const MarketCopilot = lazy(() => import("./pages/MarketCopilot"));
const Operations = lazy(() => import("./pages/Operations"));
const OptionChain = lazy(() => import("./pages/OptionChain"));
const PaperTrades = lazy(() => import("./pages/PaperTrades"));
const ProfessionalSignals = lazy(() => import("./pages/ProfessionalSignals"));
const RiskDashboard = lazy(() => import("./pages/RiskDashboard"));
const Security = lazy(() => import("./pages/Security"));
const Strategies = lazy(() => import("./pages/Strategies"));
const Subscription = lazy(() => import("./pages/Subscription"));
const Trade = lazy(() => import("./pages/Trade"));
const TradeJournal = lazy(() => import("./pages/TradeJournal"));
const TradingEngine = lazy(() => import("./pages/TradingEngine"));

function protect(path: string, page: React.ReactNode) {
  return <RequireRole path={path}>{page}</RequireRole>;
}

function subscribe(path: string, feature: string, page: React.ReactNode) {
  return protect(path, <RestrictedRoute feature={feature}>{page}</RestrictedRoute>);
}

export default function App() {
  return <BrowserRouter><AppLayout><Suspense fallback={<LoadingSkeleton />}><Routes>
    <Route path="/" element={protect("/", <Dashboard />)} />
    <Route path="/market" element={subscribe("/market", "options.basic", <OptionChain />)} />
    <Route path="/paper-trades" element={protect("/paper-trades", <PaperTrades />)} />
    <Route path="/history" element={subscribe("/history", "backtest.basic", <Backtesting />)} />
    <Route path="/settings" element={subscribe("/settings", "risk.advanced", <RiskDashboard />)} />
    <Route path="/subscription" element={protect("/subscription", <Subscription />)} />
    <Route path="/candles" element={subscribe("/candles", "chart.advanced", <Candles />)} />
    <Route path="/backtesting" element={<Navigate to="/history" replace />} />
    <Route path="/execution" element={subscribe("/execution", "paper_trade.automated", <Execution />)} />
    <Route path="/live" element={<Navigate to="/strategies" replace />} />
    <Route path="/analysis" element={<Navigate to="/strategies" replace />} />
    <Route path="/copilot" element={subscribe("/copilot", "dashboard.advanced", <MarketCopilot />)} />
    <Route path="/option-chain" element={<Navigate to="/market" replace />} />
    <Route path="/dhan-login" element={protect("/dhan-login", <DhanLogin />)} />
    <Route path="/jobs" element={protect("/jobs", <Jobs />)} />
    <Route path="/operations" element={protect("/operations", <Operations />)} />
    <Route path="/signals" element={subscribe("/signals", "signals.recent_25", <ProfessionalSignals />)} />
    <Route path="/institutional" element={subscribe("/institutional", "institutional.flow", <InstitutionalDashboard />)} />
    <Route path="/investing" element={protect("/investing", <Investing />)} />
    <Route path="/risk" element={<Navigate to="/settings" replace />} />
    <Route path="/security" element={protect("/security", <Security />)} />
    <Route path="/strategies" element={subscribe("/strategies", "strategy.performance", <Strategies />)} />
    <Route path="/trade-journal" element={subscribe("/trade-journal", "export.csv", <TradeJournal />)} />
    <Route path="/trading-engine" element={subscribe("/trading-engine", "paper_trade.automated", <TradingEngine />)} />
    <Route path="/trade" element={subscribe("/trade", "paper_trade.manual", <Trade />)} />
    <Route path="/admin/users" element={protect("/admin/users", <AdminUsers />)} />
    <Route path="/admin/notifications" element={protect("/admin/notifications", <AdminNotifications />)} />
    <Route path="*" element={<Navigate to="/" replace />} />
  </Routes></Suspense></AppLayout></BrowserRouter>;
}
