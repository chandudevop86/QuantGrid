import { useEffect, useMemo, useState } from "react";
import { api } from "../api";

type Recommendation = "BUY" | "HOLD" | "AVOID" | "WATCHLIST";

type DashboardCard = {
  category: string;
  name: string;
  score: number;
  recommendation: Recommendation;
  key_reason: string;
  risk_level: "LOW" | "MEDIUM" | "HIGH";
  allocation_suggestion: string;
};

type DashboardPayload = {
  generated_at?: string;
  summary?: string;
  disclaimer?: string;
  cards?: Record<string, DashboardCard[]>;
};

const cardTitles: Record<string, string> = {
  multibagger_candidates: "Multibagger Candidates",
  top_stock_picks: "Top Stock Picks",
  watchlist_stocks: "Watchlist Stocks",
  avoid_stocks: "Avoid Stocks",
  top_mutual_funds: "Top Mutual Funds",
  sip_ideas: "SIP Ideas",
  sector_trend: "Sector Trend",
  risk_alerts: "Risk Alerts",
};

const cardOrder = [
  "multibagger_candidates",
  "top_stock_picks",
  "watchlist_stocks",
  "avoid_stocks",
  "top_mutual_funds",
  "sip_ideas",
  "sector_trend",
  "risk_alerts",
];

function recommendationClass(value: Recommendation) {
  if (value === "BUY") return "success";
  if (value === "AVOID") return "error";
  if (value === "WATCHLIST") return "stale";
  return "";
}

function formatScore(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed.toFixed(1) : "-";
}

function formatUpdated(value?: string) {
  if (!value) return "Waiting for first research run";
  return new Date(value).toLocaleString();
}

function isRecommendation(value: unknown): value is Recommendation {
  return value === "BUY" || value === "HOLD" || value === "AVOID" || value === "WATCHLIST";
}

function isDashboardCard(value: unknown): value is DashboardCard {
  const item = value as DashboardCard;
  return Boolean(
    item &&
    typeof item.name === "string" &&
    Number.isFinite(Number(item.score)) &&
    isRecommendation(item.recommendation) &&
    typeof item.key_reason === "string" &&
    ["LOW", "MEDIUM", "HIGH"].includes(String(item.risk_level)) &&
    typeof item.allocation_suggestion === "string"
  );
}

function parseDashboardPayload(value: unknown): DashboardPayload {
  const payload = value as DashboardPayload;
  if (!payload || typeof payload !== "object" || !payload.cards || typeof payload.cards !== "object") {
    throw new Error("Investment dashboard payload is missing cards.");
  }
  for (const key of Object.keys(payload.cards)) {
    const items = payload.cards[key];
    if (!Array.isArray(items) || !items.every(isDashboardCard)) {
      throw new Error(`Investment dashboard card bucket '${key}' has an invalid shape.`);
    }
  }
  return payload;
}

function ResearchCard({ item }: { item: DashboardCard }) {
  return (
    <article className="investment-card">
      <div className="investment-card-header">
        <div>
          <h3>{item.name}</h3>
          <p>{item.category}</p>
        </div>
        <span className={`status-pill ${recommendationClass(item.recommendation)}`}>
          {item.recommendation}
        </span>
      </div>
      <div className="investment-score-row">
        <strong>{formatScore(item.score)}</strong>
        <span>Score</span>
        <strong>{item.risk_level}</strong>
        <span>Risk</span>
      </div>
      <p className="investment-reason">{item.key_reason}</p>
      <div className="investment-allocation">
        <small>Allocation</small>
        <strong>{item.allocation_suggestion}</strong>
      </div>
    </article>
  );
}

function ResearchSection({ title, items }: { title: string; items: DashboardCard[] }) {
  return (
    <section className="dashboard-section investment-section">
      <div className="form-panel-header">
        <div>
          <h2>{title}</h2>
          <p>{items.length ? `${items.length} ranked idea${items.length > 1 ? "s" : ""}` : "No qualifying ideas in the latest run"}</p>
        </div>
      </div>
      <div className="investment-grid">
        {items.map((item) => (
          <ResearchCard key={`${title}-${item.name}`} item={item} />
        ))}
        {items.length === 0 && (
          <div className="alert alert-warning" role="status">
            Latest research did not produce a card for this bucket.
          </div>
        )}
      </div>
    </section>
  );
}

export default function Investing() {
  const [payload, setPayload] = useState<DashboardPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    api.investingDashboard()
      .then((data) => {
        if (!active) return;
        setPayload(parseDashboardPayload(data));
        setError(null);
      })
      .catch((err) => {
        if (active) setError(err?.message ?? "Investment research dashboard is unavailable. Check that the backend is running.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const cards = useMemo(() => payload?.cards ?? {}, [payload]);

  return (
    <section className="dashboard-page">
      <div className="page-heading dashboard-heading">
        <div>
          <h1>Investment Research</h1>
          <p>{payload?.summary ?? "Daily stock research and weekly mutual fund rankings."}</p>
        </div>
        <div className="dashboard-actions">
          <span className="status-pill">Updated {formatUpdated(payload?.generated_at)}</span>
        </div>
      </div>

      {loading && <div className="alert" role="status">Loading investment research...</div>}
      {error && <div className="alert alert-error" role="alert">{error}</div>}

      {!loading && !error && (
        <>
          <div className="quality-banner quality-watchlist">
            <strong>Research Mode</strong>
            <span>{payload?.disclaimer ?? "Educational research, not financial advice."}</span>
          </div>

          {cardOrder.map((key) => (
            <ResearchSection key={key} title={cardTitles[key]} items={cards[key] ?? []} />
          ))}
        </>
      )}
    </section>
  );
}
