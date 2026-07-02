import { useEffect, useMemo, useState } from "react";
import { api } from "../api";

type SecurityStatus = "SECURE" | "WARNING" | "CRITICAL";
type SecuritySeverity = "CRITICAL" | "HIGH" | "WARNING" | "INFO";

type SecurityFinding = {
  title: string;
  severity: SecuritySeverity;
  affected_component: string;
  evidence: string;
  impact: string;
  fix_steps: string[];
  category: string;
};

type SecurityCard = {
  name: string;
  category: string;
  status: SecurityStatus;
  score: number;
  summary: string;
  finding_count: number;
};

type SecurityRecommendation = {
  title: string;
  priority: SecuritySeverity;
  action: string;
  affected_component: string;
};

type SecurityDashboard = {
  timestamp: string;
  overall_status: SecurityStatus;
  security_score: number;
  critical_findings: SecurityFinding[];
  warnings: SecurityFinding[];
  passed_checks: string[];
  recommended_actions: SecurityRecommendation[];
  dashboard_summary: string;
  dashboard_cards: SecurityCard[];
  trend: Array<{ timestamp: string; security_score: number; overall_status: SecurityStatus; scan_type: string }>;
};

function isStatus(value: unknown): value is SecurityStatus {
  return value === "SECURE" || value === "WARNING" || value === "CRITICAL";
}

function isSeverity(value: unknown): value is SecuritySeverity {
  return value === "CRITICAL" || value === "HIGH" || value === "WARNING" || value === "INFO";
}

function parseSecurityDashboard(value: unknown): SecurityDashboard {
  const payload = value as SecurityDashboard;
  if (!payload || typeof payload !== "object" || !isStatus(payload.overall_status) || !Array.isArray(payload.dashboard_cards)) {
    throw new Error("Security dashboard payload has an invalid shape.");
  }
  if (!payload.dashboard_cards.every((item) => item && isStatus(item.status) && Number.isFinite(Number(item.score)))) {
    throw new Error("Security dashboard cards have an invalid shape.");
  }
  const findings = [...(payload.critical_findings ?? []), ...(payload.warnings ?? [])];
  if (!findings.every((item) => item && isSeverity(item.severity) && typeof item.title === "string" && Array.isArray(item.fix_steps))) {
    throw new Error("Security findings have an invalid shape.");
  }
  return payload;
}

function statusClass(status: SecurityStatus | SecuritySeverity) {
  if (status === "SECURE") return "success";
  if (status === "CRITICAL" || status === "HIGH") return "error";
  if (status === "WARNING") return "stale";
  return "";
}

function formatTime(value?: string) {
  return value ? new Date(value).toLocaleString() : "Waiting for first scan";
}

function SecurityPostureCard({ card }: { card: SecurityCard }) {
  return (
    <article className="security-card">
      <div className="security-card-header">
        <div>
          <h3>{card.name}</h3>
          <p>{card.summary}</p>
        </div>
        <span className={`status-pill ${statusClass(card.status)}`}>{card.status}</span>
      </div>
      <div className="security-score-row">
        <strong>{Math.round(Number(card.score))}</strong>
        <span>Score</span>
        <strong>{card.finding_count}</strong>
        <span>Findings</span>
      </div>
    </article>
  );
}

function FindingList({ title, findings }: { title: string; findings: SecurityFinding[] }) {
  return (
    <section className="dashboard-section security-section">
      <div className="form-panel-header">
        <div>
          <h2>{title}</h2>
          <p>{findings.length ? `${findings.length} active item${findings.length > 1 ? "s" : ""}` : "No active items"}</p>
        </div>
      </div>
      <div className="security-finding-list">
        {findings.map((finding) => (
          <article className="security-finding" key={`${finding.category}-${finding.title}`}>
            <div>
              <span className={`status-pill ${statusClass(finding.severity)}`}>{finding.severity}</span>
              <h3>{finding.title}</h3>
              <p>{finding.impact}</p>
              <small>{finding.affected_component}</small>
            </div>
            <div>
              <strong>Fix</strong>
              <p>{finding.fix_steps[0] ?? "Review and document remediation."}</p>
            </div>
          </article>
        ))}
        {findings.length === 0 && <div className="alert">No findings in this bucket.</div>}
      </div>
    </section>
  );
}

export default function Security() {
  const [payload, setPayload] = useState<SecurityDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    api.securityDashboard()
      .then((data) => {
        if (!active) return;
        setPayload(parseSecurityDashboard(data));
        setError(null);
      })
      .catch((err) => {
        if (active) setError(err?.message ?? "Security dashboard is unavailable.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const findings = useMemo(() => [...(payload?.critical_findings ?? []), ...(payload?.warnings ?? [])], [payload]);
  const trend = payload?.trend ?? [];

  return (
    <section className="dashboard-page">
      <div className="page-heading dashboard-heading">
        <div>
          <h1>Security Operations</h1>
          <p>{payload?.dashboard_summary ?? "Continuous DevSecOps posture across network, API, Kubernetes, containers, IAM, database, and pipeline controls."}</p>
        </div>
        <div className="dashboard-actions">
          <span className={`status-pill ${payload ? statusClass(payload.overall_status) : ""}`}>{payload?.overall_status ?? "LOADING"}</span>
          <span className="status-pill">Updated {formatTime(payload?.timestamp)}</span>
        </div>
      </div>

      {loading && <div className="alert" role="status">Loading security posture...</div>}
      {error && <div className="alert alert-error" role="alert">{error}</div>}

      {!loading && !error && payload && (
        <>
          <div className="security-overview">
            <article className="security-score-panel">
              <span>Overall Security Score</span>
              <strong>{Math.round(Number(payload.security_score))}</strong>
              <p>{payload.passed_checks.length} controls passed</p>
            </article>
            <div className="security-grid">
              {payload.dashboard_cards.map((card) => (
                <SecurityPostureCard key={card.category} card={card} />
              ))}
            </div>
          </div>

          <section className="dashboard-section security-section">
            <div className="form-panel-header">
              <div>
                <h2>Trend</h2>
                <p>{trend.length ? `${trend.length} stored scan result${trend.length > 1 ? "s" : ""}` : "Trend appears after scheduled scans run"}</p>
              </div>
            </div>
            <div className="security-trend">
              {trend.map((point) => (
                <div key={`${point.timestamp}-${point.scan_type}`} className="security-trend-point">
                  <span style={{ height: `${Math.max(8, Number(point.security_score))}%` }} />
                  <small>{Number(point.security_score)}</small>
                </div>
              ))}
              {trend.length === 0 && <div className="alert">No scan history has been stored yet.</div>}
            </div>
          </section>

          <FindingList title="Critical Findings" findings={payload.critical_findings} />
          <FindingList title="Warnings And High-Risk Items" findings={payload.warnings} />

          <section className="dashboard-section security-section">
            <div className="form-panel-header">
              <div>
                <h2>Recommended Fixes</h2>
                <p>{payload.recommended_actions.length ? "Prioritized by severity" : "No recommendations"}</p>
              </div>
            </div>
            <div className="security-recommendations">
              {payload.recommended_actions.map((item) => (
                <article className="security-recommendation" key={`${item.affected_component}-${item.title}`}>
                  <span className={`status-pill ${statusClass(item.priority)}`}>{item.priority}</span>
                  <div>
                    <h3>{item.title}</h3>
                    <p>{item.action}</p>
                    <small>{item.affected_component}</small>
                  </div>
                </article>
              ))}
              {payload.recommended_actions.length === 0 && <div className="alert">All tracked controls are passing.</div>}
            </div>
          </section>
        </>
      )}
    </section>
  );
}
