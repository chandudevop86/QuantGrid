import { useEffect, useState } from "react";
import { api } from "../api";

type CopilotPayload = {
  generated_at?: string;
  summary?: string;
  signal_explanation?: {
    scenario?: string;
    reason?: string;
    why_now?: string;
    patterns?: string[];
    expiry_warning?: string;
    option_context?: string;
  };
  bullish_reasons?: string[];
  bearish_reasons?: string[];
  invalidation_level?: number | null;
  invalidation_text?: string;
  confidence_score?: number;
  market_regime?: string;
  market_narrative?: string;
  what_changed?: string[];
  guardrails?: string[];
};

function formatNumber(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed.toFixed(2) : "-";
}

function ListPanel({ title, items }: { title: string; items?: string[] }) {
  return (
    <section className="form-panel signal-panel">
      <div className="form-panel-header">
        <div>
          <h2>{title}</h2>
          <p>{items?.length ? `${items.length} item${items.length > 1 ? "s" : ""}` : "No material items"}</p>
        </div>
      </div>
      <div className="diagnostic-list">
        {(items ?? []).map((item) => (
          <span key={item}>{item}</span>
        ))}
        {(!items || items.length === 0) && <span>-</span>}
      </div>
    </section>
  );
}

export default function MarketCopilot() {
  const [payload, setPayload] = useState<CopilotPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    api.marketCopilot()
      .then((data) => {
        setPayload(data);
        setError(null);
      })
      .catch((err) => setError(err?.message ?? "Market Copilot is unavailable."))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const explanation = payload?.signal_explanation ?? {};

  return (
    <section className="dashboard-page">
      <div className="page-heading dashboard-heading">
        <div>
          <h1>AI Market Copilot</h1>
          <p>Explain market context, signal reasoning, invalidation, confidence, and changes.</p>
        </div>
        <div className="dashboard-actions">
          <span className="status-pill">{payload?.market_regime ?? "Loading"}</span>
          <button className="refresh-button" type="button" onClick={load} disabled={loading}>
            Refresh
          </button>
        </div>
      </div>

      {loading && <div className="alert" role="status">Loading Market Copilot...</div>}
      {error && <div className="alert alert-error" role="alert">{error}</div>}

      {!loading && !error && (
        <>
          <div className="quality-banner quality-watchlist">
            <strong>{explanation.scenario ?? "Scenario watch"}</strong>
            <span>{payload?.summary ?? "Explanation only."}</span>
          </div>

          <div className="metric-grid">
            <article className="metric-card">
              <span className="metric-label">Confidence</span>
              <strong className="metric-value">{payload?.confidence_score ?? 0}%</strong>
              <span className="metric-helper">Context confidence, not execution approval</span>
            </article>
            <article className="metric-card">
              <span className="metric-label">Invalidation</span>
              <strong className="metric-value">{formatNumber(payload?.invalidation_level)}</strong>
              <span className="metric-helper">{payload?.invalidation_text ?? "Re-evaluate on fresh confirmation"}</span>
            </article>
            <article className="metric-card">
              <span className="metric-label">Pattern Count</span>
              <strong className="metric-value">{explanation.patterns?.length ?? 0}</strong>
              <span className="metric-helper">{explanation.patterns?.join(", ") || "No clear pattern cluster"}</span>
            </article>
          </div>

          <section className="form-panel signal-panel">
            <div className="form-panel-header">
              <div>
                <h2>Market Narrative</h2>
                <p>{payload?.market_narrative}</p>
              </div>
            </div>
            <div className="signal-summary">
              <span>
                <strong>{explanation.reason ?? "-"}</strong>
                Reason
              </span>
              <span>
                <strong>{explanation.why_now ?? "-"}</strong>
                Why now
              </span>
              <span>
                <strong>{explanation.option_context ?? "-"}</strong>
                Option context
              </span>
            </div>
            {explanation.expiry_warning && (
              <div className="alert alert-warning" role="status">{explanation.expiry_warning}</div>
            )}
          </section>

          <div className="strategy-signal-grid">
            <ListPanel title="Bullish Reasons" items={payload?.bullish_reasons} />
            <ListPanel title="Bearish Reasons" items={payload?.bearish_reasons} />
            <ListPanel title="What Changed" items={payload?.what_changed} />
            <ListPanel title="Guardrails" items={payload?.guardrails} />
          </div>

          <div className="alert alert-success">
            Copilot explains context only. It does not place trades or replace strategy, risk, and execution checks.
          </div>
        </>
      )}
    </section>
  );
}
