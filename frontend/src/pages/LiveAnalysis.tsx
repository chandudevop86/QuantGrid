import { useState, useEffect } from "react";
import { api } from "../api/dashboard";

export default function LiveAnalysis() {
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    try {
      setLoading(true);
      setError(null);

      const res = await api.runAnalysis({
        symbol: "NIFTY",
        interval: "1m",
        period: "1d",
        strategy: "breakout",
        capital: 100000,
        risk_pct: 1,
        rr_ratio: 2,
      });

      // 🔥 assume backend returns job_id
      setJobId(res.job_id);
      setResult(res);
    } catch (err: any) {
      console.error(err);
      setError("Failed to run analysis");
    } finally {
      setLoading(false);
    }
  };

  // 🔥 Real-time updates via WebSocket
  useEffect(() => {
    if (!jobId) return;

    const ws = new WebSocket("ws://YOUR_EC2_IP:8005/ws");

    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);

      // only update relevant job
      if (data.job_id === jobId) {
        setResult(data);
      }
    };

    return () => ws.close();
  }, [jobId]);

  return (
    <div>
      <h1 className="text-xl mb-4">Live Analysis</h1>

      <button
        onClick={run}
        disabled={loading}
        className="bg-blue-500 px-4 py-2 rounded"
      >
        {loading ? "Running..." : "Run Analysis"}
      </button>

      {error && <p className="text-red-500 mt-2">{error}</p>}

      <pre className="mt-4 bg-gray-900 p-4">
        {result
          ? JSON.stringify(result, null, 2)
          : "No data yet..."}
      </pre>
    </div>
  );
}