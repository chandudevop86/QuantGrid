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

type QualityGrowthItem = {
  symbol: string;
  name: string;
  market_cap_bucket?: string | null;
  score: number;
  fundamentals_as_of: string;
  price_as_of: string;
  reasons: string[];
  research_priority?: string;
};
type QualityGrowthPayload = {
  status: "READY" | "UNAVAILABLE" | "UNCONFIGURED";
  source: string;
  as_of?: string;
  refreshed_at?: string;
  qualified_count: number;
  items: QualityGrowthItem[];
  excluded: Array<{ symbol: string; reasons: string[]; status: string }>;
  reason?: string;
  disclaimer: string;
};

function QualityGrowthWatchlist() {
  const [snapshot, setSnapshot] = useState<QualityGrowthPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [feedError, setFeedError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    const update = () => {
      api.qualityGrowthScreen()
        .then((data: QualityGrowthPayload) => {
          if (!mounted) return;
          if (!data || !Array.isArray(data.items) || !Array.isArray(data.excluded)) {
            throw new Error("Invalid quality-growth response");
          }
          setSnapshot(data);
          setFeedError(null);
        })
        .catch((error: unknown) => {
          if (mounted) setFeedError(error instanceof Error ? error.message : "Screen feed unavailable");
        })
        .finally(() => { if (mounted) setLoading(false); });
    };
    update();
    const timer = window.setInterval(update, 300000);
    return () => { mounted = false; window.clearInterval(timer); };
  }, []);

  return (
    <section className="dashboard-section investment-section" aria-label="Quality Growth V2">
      <div className="form-panel-header">
        <div>
          <h2>Quality Growth V2 — Research Watchlist</h2>
          <p>30 quality · 25 growth · 20 valuation · 15 momentum · 10 risk.
            Auto-checks the verified source every 5 minutes while this page is open.</p>
        </div>
      </div>
      {loading && <p>Checking licensed screening feed...</p>}
      {feedError && <div className="alert alert-error" role="alert">{feedError}</div>}
      {snapshot && (
        <>
          <p><strong>{snapshot.status}</strong> · {snapshot.qualified_count} qualified ·
            Source: {snapshot.source} · Data as of: {snapshot.as_of ?? "unavailable"}</p>
          {snapshot.status !== "READY" && (
            <div className="alert alert-warning" role="status">
              {snapshot.reason ?? "Verified screening data is unavailable."}
              {" "}No fabricated stocks or buy signals are shown.
            </div>
          )}
          <p className="metric-helper">{snapshot.disclaimer}</p>
          {snapshot.items.length > 0 && (
            <div className="investment-grid">
              {snapshot.items.map((item) => (
                <article className="investment-card" key={item.symbol}>
                  <div className="investment-card-header">
                    <div><h3>{item.symbol} — {item.name}</h3>
                      <p>{item.market_cap_bucket ?? "Unclassified"} · {item.research_priority ?? "RESEARCH"}</p></div>
                    <span className="status-pill">{item.score.toFixed(1)} / 100</span>
                  </div>
                  <p>Financials: {item.fundamentals_as_of} · Price: {item.price_as_of}</p>
                  {item.reasons.length > 0 && <p>{item.reasons.join("; ")}</p>}
                </article>
              ))}
            </div>
          )}
          {snapshot.status === "READY" && (
            <p className="metric-helper">{snapshot.excluded.length} stocks did not pass or could not be verified.
              This screen is for research, not trade execution.</p>
          )}
        </>
      )}
    </section>
  );
}

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

      <QualityGrowthWatchlist />

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
