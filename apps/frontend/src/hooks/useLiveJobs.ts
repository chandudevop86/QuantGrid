import { useEffect, useState } from "react";
import { api } from "../api";
import { hasAuthToken } from "../roles";
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
    if (!hasAuthToken()) {
      setJobs([]);
      setError(null);
      setSocketConnected(false);
      return;
    }

    let active = true;
    let socket: WebSocket | null = null;
    let pollId: number | null = null;
    let reconnectId: number | null = null;
    let reconnectAttempts = 0;
    // Once the socket has failed this many times in a row, stop trying every few seconds and
    // fall back to a slow, steady retry cadence instead -- this used to retry every 3s
    // forever with no backoff, which (combined with the 3s polling fallback running at the
    // same time) meant a persistently-down socket endpoint produced constant double-traffic
    // (a new WS handshake attempt AND a poll request every 3 seconds) for as long as the
    // Jobs page stayed open.
    const maxFastReconnectAttempts = 5;

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
        reconnectAttempts = 0;
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
        reconnectAttempts += 1;
        const delay =
          reconnectAttempts <= maxFastReconnectAttempts
            ? Math.min(30000, 1000 * 2 ** (reconnectAttempts - 1))
            : 30000;
        reconnectId = window.setTimeout(connect, delay);
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
