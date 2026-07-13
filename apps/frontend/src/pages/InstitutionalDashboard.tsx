import { useEffect, useMemo, useState } from "react";
import { api } from "../api";

type Metric = {
  label: string;
  value: number | null;
  unit?: string | null;
  source?: string;
  env_name?: string;
};

type OiLeader = {
  strike: number;
  oi: number;
} | null;

type InstitutionalPayload = {
  generated_at?: string;
  symbol?: string;
  cash_flows?: Record<string, Metric>;
  futures?: Record<string, Metric>;
  derivatives?: {
    source?: string;
    provider_available?: boolean;
    pcr?: number | null;
    max_pain?: number | null;
    highest_call_oi?: OiLeader;
    highest_put_oi?: OiLeader;
    oi_change?: { call?: number | null; put?: number | null; net?: number | null };
    updated_at?: string | null;
  };
  macro?: Record<string, Metric>;
  global_indices?: Array<{ label: string; value?: number | null; change_pct?: number | null; source?: string }>;
  market_narrative?: string;
  warnings?: string[];
  data_policy?: string;
};

function formatNumber(value: unknown, suffix?: string | null) {
  if (value === null || value === undefined || value === "") return "-";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "-";
  const formatted = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(parsed);
  return suffix ? `${formatted} ${suffix}` : formatted;
}

function formatUpdated(value?: string | null) {
  if (!value) return "Waiting for data";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Waiting for data" : date.toLocaleString();
}

function metricItems(payload: InstitutionalPayload | null) {
  const cash = payload?.cash_flows ?? {};
  const futures = payload?.futures ?? {};
  const macro = payload?.macro ?? {};
  return [
    cash.fii_cash,
    cash.dii_cash,
    futures.fii_index_futures,
    macro.gift_nifty,
    macro.india_vix,
    macro.usd_inr,
    macro.crude_oil,
    macro.gold,
  ].filter(Boolean) as Metric[];
}

function MetricCard({ item }: { item: Metric }) {
  const unavailable = item.source === "unavailable";
  return (
    <article className={`metric-card${unavailable ? " metric-card-warn" : " metric-card-good"}`}>
      <span className="metric-label">{item.label}</span>
      <strong className="metric-value">{formatNumber(item.value, item.unit)}</strong>
      <span className="metric-helper">{unavailable ? `Set ${item.env_name ?? "env input"}` : `Source: ${item.source ?? "configured"}`}</span>
    </article>
  );
}

function OiCard({ label, item }: { label: string; item: OiLeader }) {
  return (
    <article className="metric-card">
      <span className="metric-label">{label}</span>
      <strong className="metric-value">{item ? formatNumber(item.strike) : "-"}</strong>
      <span className="metric-helper">{item ? `OI ${formatNumber(item.oi)}` : "Live option chain unavailable"}</span>
    </article>
  );
}

export default function InstitutionalDashboard() {
  const [payload, setPayload] = useState<InstitutionalPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    api.institutionalDashboard()
      .then((data) => {
        setPayload(data);
        setError(null);
      })
      .catch((err) => {
        setError(err?.message ?? "Institutional dashboard is unavailable.");
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const metrics = useMemo(() => metricItems(payload), [payload]);
  const derivatives = payload?.derivatives;
  const warnings = payload?.warnings ?? [];

  return (
    <section className="dashboard-page">
      <div className="page-heading dashboard-heading">
        <div>
          <h1>Institutional Dashboard</h1>
          <p>FII/DII flows, macro cues, option positioning, and market narrative.</p>
        </div>
        <div className="dashboard-actions">
          <span className={`status-pill${derivatives?.provider_available ? "" : " stale"}`}>
            {derivatives?.provider_available ? "LIVE OPTIONS" : "WATCH MODE"}
          </span>
          <button className="refresh-button" type="button" onClick={load} disabled={loading}>
            Refresh
          </button>
        </div>
      </div>

      {loading && <div className="alert" role="status">Loading institutional dashboard...</div>}
      {error && <div className="alert alert-error" role="alert">{error}</div>}

      {!loading && !error && (
        <>
          <div className="quality-banner quality-watchlist">
            <strong>{payload?.symbol ?? "NIFTY"}</strong>
            <span>Updated {formatUpdated(payload?.generated_at)}</span>
          </div>

          <section className="dashboard-section">
            <div className="metric-grid">
              {metrics.map((item) => (
                <MetricCard key={item.label} item={item} />
              ))}
            </div>
          </section>

          <section className="dashboard-section">
            <div className="section-header">
              <div>
                <h2>Derivatives</h2>
                <span>Source: {derivatives?.source ?? "unavailable"} | Updated {formatUpdated(derivatives?.updated_at)}</span>
              </div>
            </div>
            <div className="metric-grid">
              <article className="metric-card">
                <span className="metric-label">PCR</span>
                <strong className="metric-value">{formatNumber(derivatives?.pcr)}</strong>
                <span className="metric-helper">Put/call open interest</span>
              </article>
              <article className="metric-card">
                <span className="metric-label">Max Pain</span>
                <strong className="metric-value">{formatNumber(derivatives?.max_pain)}</strong>
                <span className="metric-helper">From live option chain only</span>
              </article>
              <OiCard label="Highest Call OI" item={derivatives?.highest_call_oi ?? null} />
              <OiCard label="Highest Put OI" item={derivatives?.highest_put_oi ?? null} />
              <article className="metric-card">
                <span className="metric-label">Call OI Change</span>
                <strong className="metric-value">{formatNumber(derivatives?.oi_change?.call)}</strong>
                <span className="metric-helper">Sum across returned strikes</span>
              </article>
              <article className="metric-card">
                <span className="metric-label">Put OI Change</span>
                <strong className="metric-value">{formatNumber(derivatives?.oi_change?.put)}</strong>
                <span className="metric-helper">Net {formatNumber(derivatives?.oi_change?.net)}</span>
              </article>
            </div>
          </section>

          <section className="dashboard-section">
            <div className="form-panel signal-panel">
              <div className="form-panel-header">
                <div>
                  <h2>Market Narrative</h2>
                  <p>{payload?.market_narrative ?? "Waiting for institutional inputs."}</p>
                </div>
              </div>
              <div className="signal-trade-grid">
                {(payload?.global_indices ?? []).map((item) => (
                  <span key={item.label}>
                    <small>{item.label}</small>
                    <strong>{formatNumber(item.value)}</strong>
                    <small>{formatNumber(item.change_pct)}%</small>
                  </span>
                ))}
                {payload?.global_indices?.length === 0 && (
                  <span>
                    <small>Global Indices</small>
                    <strong>-</strong>
                    <small>Configure GLOBAL_INDICES_JSON</small>
                  </span>
                )}
              </div>
            </div>
          </section>

          {warnings.length > 0 && (
            <div className="alert alert-warning" role="status">
              {warnings.join(" ")}
            </div>
          )}
          {payload?.data_policy && <div className="alert alert-success">{payload.data_policy}</div>}
        </>
      )}
    </section>
  );
}
