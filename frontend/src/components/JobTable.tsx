import { useEffect, useState } from "react";
import { api } from "../api/dashboard";

export default function Jobs() {
  const [jobs, setJobs] = useState<any>(null);

  useEffect(() => {
    api.jobs().then(setJobs);
  }, []);

  return (
    <div>
      <h2 className="text-xl mb-4">Live Analysis Jobs</h2>

      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-gray-400">
            <th>ID</th>
            <th>Status</th>
            <th>Symbol</th>
            <th>Strategy</th>
          </tr>
        </thead>

        <tbody>
          {jobs?.jobs?.map((j: any) => (
            <tr key={j.job_id} className="border-b border-gray-800">
              <td>{j.job_id}</td>
              <td>{j.status}</td>
              <td>{j.symbol}</td>
              <td>{j.strategy}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}