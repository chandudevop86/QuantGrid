import { useEffect, useMemo, useState } from "react";
import { api } from "../api";

const refreshMs = 30000;
const staleWarningMinutes = 10;

function formatIstTime(date: Date) {
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

function formatCandleTime(value: unknown) {
  if (!value) return "-";
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? "-" : formatIstTime(date);
}

function candleAgeMinutes(value: unknown, now: Date) {
  if (!value) return null;
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return null;
  return Math.max(0, Math.floor((now.getTime() - date.getTime()) / 60000));
}

function formatAge(age: number | null) {
  if (age === null) return "-";
  if (age < 1) return "<1m";
  if (age < 60) return `${age}m`;
  const hours = Math.floor(age / 60);
  const minutes = age % 60;
  return minutes ? `${hours}h ${minutes}m` : `${hours}h`;
}

export default function MarketStatusBanner() {
  const [operations, setOperations] = useState<any>(null);
  const [now, setNow] = useState(new Date());
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;

    const load = async () => {
      try {
        const data = await api.operationsStatus();
        if (!active) return;
        setOperations(data);
        setError(false);
      } catch {
        if (active) setError(true);
      }
    };

    void load();
    const refreshId = window.setInterval(load, refreshMs);
    const clockId = window.setInterval(() => setNow(new Date()), 1000);

    return () => {
      active = false;
      window.clearInterval(refreshId);
      window.clearInterval(clockId);
    };
  }, []);

  const market = operations?.market_status;
  const sessionOpen = String(market?.session_state ?? "").toLowerCase() === "open";
  const marketOpen = sessionOpen && String(market?.state ?? "").toLowerCase() !== "holiday";
  const latestCandle = market?.last_candle_timestamp;
  const age = useMemo(() => candleAgeMinutes(latestCandle, now), [latestCandle, now]);
  const warning = marketOpen && age !== null && age > staleWarningMinutes;

  if (error && !operations) {
    return (
      <div className="market-banner market-banner-warning" role="status">
        <strong>NSE STATUS UNKNOWN</strong>
        <span>IST {formatIstTime(now)}</span>
        <span>Market status API unavailable</span>
      </div>
    );
  }

  return (
    <div className={`market-banner ${marketOpen ? "market-banner-open" : "market-banner-closed"}${warning ? " market-banner-warning" : ""}`} role="status">
      <strong>NSE {marketOpen ? "OPEN" : "CLOSED"}</strong>
      <span>IST {formatIstTime(now)}</span>
      <span>Latest candle {formatCandleTime(latestCandle)}</span>
      <span>Age {formatAge(age)}</span>
      {!marketOpen && <span>NSE CLOSED - Last candle from previous session</span>}
      {warning && <span>Candle age above 10 minutes during market hours</span>}
    </div>
  );
}
