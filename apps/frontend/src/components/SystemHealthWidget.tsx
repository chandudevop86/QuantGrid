import { useEffect, useMemo, useState } from "react";
import { api } from "../api";

type HealthTone = "green" | "yellow" | "red";

type HealthBadgeProps = {
  label: string;
  status: string;
  tone: HealthTone;
  helper?: string;
};

type SystemHealthWidgetProps = {
  operations?: any;
  websocketConnected?: boolean;
  websocketStatus?: "online" | "offline" | "polling";
  compact?: boolean;
};

function formatAge(seconds?: number | null) {
  if (typeof seconds !== "number" || Number.isNaN(seconds)) return "-";
  const absolute = Math.abs(seconds);
  if (absolute < 60) return `${Math.round(seconds)}s`;
  if (absolute < 3600) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toFixed(1)}h`;
}

function healthOk(payload: any) {
  return payload?.status === "ok" || payload?.status === "ready" || payload?.healthy === true;
}

function HealthBadge({ label, status, tone, helper }: HealthBadgeProps) {
  return (
    <span className={`health-badge health-badge-${tone}`}>
      <small>{label}</small>
      <strong>{status}</strong>
      {helper && <em>{helper}</em>}
    </span>
  );
}

export default function SystemHealthWidget({ operations, websocketConnected, websocketStatus, compact = false }: SystemHealthWidgetProps) {
  const [apiHealth, setApiHealth] = useState<any>(null);
  const [localOperations, setLocalOperations] = useState<any>(operations ?? null);
  const [apiReachable, setApiReachable] = useState(false);

  useEffect(() => {
    if (operations) setLocalOperations(operations);
  }, [operations]);

  useEffect(() => {
    let active = true;

    const load = async () => {
      try {
        const [health, status] = await Promise.all([
          api.health(),
          operations ? Promise.resolve(operations) : api.operationsStatus(),
        ]);
        if (!active) return;
        setApiHealth(health);
        setLocalOperations(status);
        setApiReachable(true);
      } catch {
        if (!active) return;
        setApiReachable(false);
      }
    };

    void load();
    const id = window.setInterval(load, 30000);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, [operations]);

  const health = localOperations?.system_health;
  const market = localOperations?.market_status;
  const latestCandleAge = market?.feed_delay_seconds;
  const marketOpen = market?.session_state === "open";
  const staleMarketData = marketOpen && typeof latestCandleAge === "number" && latestCandleAge > 600;
  const websocketOnline = websocketConnected === true || health?.websocket?.active === true;
  const realtimeStatus = websocketOnline ? "Online" : websocketStatus === "polling" ? "Polling fallback" : "Offline";
  const redisConfigured = health?.redis?.message !== "REDIS_URL is not configured.";

  const badges = useMemo(
    () => [
      {
        label: "API",
        status: apiReachable && healthOk(apiHealth) ? "Healthy" : "Offline",
        tone: apiReachable && healthOk(apiHealth) ? "green" : "red",
        helper: "/api/health",
      },
      {
        label: "WebSocket",
        status: realtimeStatus,
        tone: websocketOnline ? "green" : "yellow",
        helper: websocketOnline ? `${health?.websocket?.connections ?? 0} client(s)` : realtimeStatus === "Polling fallback" ? "Polling after socket failure" : "Reconnect backoff active",
      },
      {
        label: "Market Data",
        status: staleMarketData ? "Stale" : market?.last_candle_timestamp ? "Fresh" : "Waiting",
        tone: staleMarketData ? "yellow" : market?.last_candle_timestamp ? "green" : "red",
        helper: `Latest ${formatAge(latestCandleAge)}`,
      },
      {
        label: "Backend Service",
        status: localOperations ? "Running" : "Unavailable",
        tone: localOperations ? "green" : "red",
        helper: localOperations?.updated_at ? "Operations online" : "No operations status",
      },
      {
        label: "Redis",
        status: health?.redis?.connected ? "Healthy" : redisConfigured ? "Offline" : "Not configured",
        tone: health?.redis?.connected ? "green" : redisConfigured ? "red" : "yellow",
        helper: health?.redis?.message,
      },
    ] as HealthBadgeProps[],
    [apiHealth, apiReachable, health, latestCandleAge, localOperations, realtimeStatus, redisConfigured, staleMarketData, websocketOnline],
  );

  const attention = badges.some((badge) => badge.tone === "red") ? "Needs attention" : badges.some((badge) => badge.tone === "yellow") ? "Review" : "Healthy";

  return (
    <section className={`system-health-widget${compact ? " system-health-widget-compact" : ""}`} aria-label="System health">
      <div className="system-health-header">
        <div>
          <h2>System Health</h2>
          <p>{websocketOnline ? "Realtime channel connected." : realtimeStatus === "Polling fallback" ? "WebSocket is offline. Fallback polling is active." : "WebSocket reconnect backoff is active."}</p>
        </div>
        <strong className={`system-health-summary system-health-summary-${attention === "Healthy" ? "green" : attention === "Review" ? "yellow" : "red"}`}>
          {attention}
        </strong>
      </div>
      <div className="system-health-badges">
        {badges.map((badge) => (
          <HealthBadge key={badge.label} {...badge} />
        ))}
      </div>
    </section>
  );
}
