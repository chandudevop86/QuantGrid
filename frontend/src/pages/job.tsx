
export { default } from "./Jobs";


export { default } from "./Jobs";

import { useEffect, useState } from "react";
import { api } from "../../services/api";

export default function Jobs() {
  const [jobs, setJobs] = useState<any[]>([]);

  useEffect(() => {
    api.getJobs().then((res) => setJobs(res.jobs));
  }, []);

  return (
    <div>
      <h2>Live Jobs</h2>

      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Status</th>
            <th>Symbol</th>
          </tr>
        </thead>

        <tbody>
          {jobs.map((j) => (
            <tr key={j.job_id}>
              <td>{j.job_id}</td>
              <td>{j.status}</td>
              <td>{j.symbol}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
