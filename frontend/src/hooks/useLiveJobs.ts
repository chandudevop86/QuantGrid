import { useEffect, useState } from "react";
import { api } from "../api";
import { createSocket } from "../socket";

function mergeJob(jobs: any[], incoming: any) {
  const jobId = incoming?.job_id ?? incoming?.id;
  if (!jobId) return jobs;

  const index = jobs.findIndex((job) => (job.job_id ?? job.id) === jobId);
  if (index === -1) {
    return [incoming, ...jobs];
  }

  const nextJobs = [...jobs];
  nextJobs[index] = { ...nextJobs[index], ...incoming };
  return nextJobs;
}

export function useLiveJobs() {
  const [jobs, setJobs] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [socketConnected, setSocketConnected] = useState(false);

  useEffect(() => {
    let active = true;
    let socket: WebSocket | null = null;
    let pollId: number | null = null;
    let reconnectId: number | null = null;

    const fetchJobs = async () => {
      try {
        const res = await api.getJobs();
        if (!active) return;
        setJobs(Array.isArray(res?.jobs) ? res.jobs : []);
        setError(null);
      } catch {
        if (active) {
          setError("Jobs API is not available yet.");
        }
      }
    };

    const stopPolling = () => {
      if (pollId !== null) {
        window.clearInterval(pollId);
        pollId = null;
      }
    };

    const startPolling = () => {
      if (pollId !== null) return;
      void fetchJobs();
      pollId = window.setInterval(fetchJobs, 3000);
    };

    const connect = () => {
      socket = createSocket();

      socket.onopen = () => {
        if (!active) return;
        setSocketConnected(true);
        stopPolling();
        void fetchJobs();
      };

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setJobs((current) => mergeJob(current, data));
        } catch {
          setError("Received an invalid live job update.");
        }
      };

      socket.onerror = () => {
        socket?.close();
      };

      socket.onclose = () => {
        if (!active) return;
        setSocketConnected(false);
        startPolling();
        reconnectId = window.setTimeout(connect, 3000);
      };
    };

    void fetchJobs();
    connect();

    return () => {
      active = false;
      stopPolling();
      if (reconnectId !== null) window.clearTimeout(reconnectId);
      socket?.close();
    };
  }, []);

  return { jobs, error, socketConnected };
}
