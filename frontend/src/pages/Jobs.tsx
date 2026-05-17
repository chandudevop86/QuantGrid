import { useLiveJobs } from "../hooks/useLiveJobs";

export default function Jobs() {
  const { jobs, error, socketConnected } = useLiveJobs();

  return (
    <section className="dashboard-page">
      <div className="page-heading">
        <h1>Live Jobs</h1>
        <p>Analysis jobs submitted to the trading service.</p>
      </div>
      {!socketConnected && !error && (
        <p className="warning-text">Live websocket unavailable. Polling jobs every 3 seconds.</p>
      )}
      {error && <p className="error-text">{error}</p>}
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Status</th>
              <th>Symbol</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.job_id ?? job.id}>
                <td>{job.job_id ?? job.id}</td>
                <td>{job.status ?? "unknown"}</td>
                <td>{job.symbol ?? "-"}</td>
              </tr>
            ))}
            {jobs.length === 0 && (
              <tr>
                <td colSpan={3}>No jobs have been created yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
