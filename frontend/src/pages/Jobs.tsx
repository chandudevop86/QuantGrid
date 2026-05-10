import { useEffect, useState } from "react";
import { api } from "../api";

export default function Jobs() {
  const [jobs, setJobs] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getJobs()
      .then((res) => setJobs(Array.isArray(res?.jobs) ? res.jobs : []))
      .catch(() => setError("Jobs API is not available yet."));
  }, []);

  return (
    <section>
      <h1>Live Jobs</h1>
      {error && <p style={{ color: "#f87171" }}>{error}</p>}
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
        </tbody>
      </table>
    </section>
  );
}
