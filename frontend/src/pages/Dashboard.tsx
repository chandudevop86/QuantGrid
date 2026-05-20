import { useEffect, useState } from "react";
import { api } from "../api";
import Loader from "../components/Loader";
import MetricCard from "../components/MetricCard";
import { useLiveJobs } from "../hooks/useLiveJobs";
import { hasAuthToken } from "../roles";

function isActiveJob(job: any) {
  return ["queued", "running"].includes(String(job?.status ?? "").toLowerCase());
}

export default function Dashboard() {
  const [summary, setSummary] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const isAuthenticated = hasAuthToken();
  const { jobs, error: jobsError } = useLiveJobs();

  useEffect(() => {
    if (!isAuthenticated) {
      setLoading(false);
      return;
    }

    api
      .getSummary()
      .then(setSummary)
      .catch(() => setError("Dashboard API is not available yet."))
      .finally(() => setLoading(false));
  }, [isAuthenticated]);

  const activeJobs = jobs.filter(isActiveJob).length;
  const lastUpdated = summary?.updated_at
    ? new Date(summary.updated_at).toLocaleString()
    : "Not available";

  return (
    <section className="dashboard-page">
      <div className="page-heading">
        <div>
          <h1>QuantGrid Dashboard</h1>
          <p>Service health, live-analysis jobs, and trading activity at a glance.</p>
        </div>
      </div>

      {!isAuthenticated && (
        <div className="alert alert-warning" role="status">
          Login with an authorized account to view dashboard data and trading workflows.
        </div>
      )}

      {isAuthenticated && loading && <Loader label="Loading dashboard..." />}
      {(error || jobsError) && <p className="error-text">{error ?? jobsError}</p>}

      {isAuthenticated && !loading && !error && !jobsError && (
        <>
          <div className="metric-grid">
            <MetricCard
              label="API Status"
              value={summary?.status ?? "unknown"}
              helper={`Updated ${lastUpdated}`}
              tone={summary?.status === "ready" ? "good" : "warn"}
            />
            <MetricCard
              label="Active Jobs"
              value={activeJobs}
              helper={`${jobs.length} total jobs`}
            />
            <MetricCard
              label="Open Positions"
              value={summary?.open_positions ?? 0}
              helper="Paper execution mode"
            />
          </div>

          <div className="dashboard-section">
            <div className="section-header">
              <h2>Recent Jobs</h2>
              <span>{jobs.length} total</span>
            </div>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Status</th>
                    <th>Symbol</th>
                    <th>Strategy</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.slice(0, 5).map((job) => (
                    <tr key={job.job_id ?? job.id}>
                      <td>{job.job_id ?? job.id}</td>
                      <td>{job.status ?? "unknown"}</td>
                      <td>{job.symbol ?? "-"}</td>
                      <td>{job.strategy ?? "-"}</td>
                    </tr>
                  ))}
                  {jobs.length === 0 && (
                    <tr>
                      <td colSpan={4}>No live-analysis jobs yet.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
