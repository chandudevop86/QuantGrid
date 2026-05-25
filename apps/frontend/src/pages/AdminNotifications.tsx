import { useEffect, useState } from "react";
import { api } from "../api";
import { getApiErrorMessage } from "../api/client";

type NotificationStatus = {
  alerts_enabled: boolean;
  channels: {
    telegram: boolean;
    slack: boolean;
    email: boolean;
  };
  configured_recipients: {
    telegram_chat: boolean;
    email_recipients: number;
  };
};

const channelLabels: Record<keyof NotificationStatus["channels"], string> = {
  telegram: "Telegram",
  slack: "Slack",
  email: "Email",
};

export default function AdminNotifications() {
  const [status, setStatus] = useState<NotificationStatus | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [testing, setTesting] = useState(false);

  const loadStatus = () => {
    setLoading(true);
    setError(null);
    api
      .getNotificationStatus()
      .then(setStatus)
      .catch((err: any) => setError(getApiErrorMessage(err, "Unable to load notification status.")))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadStatus();
  }, []);

  const sendTest = async () => {
    setTesting(true);
    setMessage(null);
    setError(null);
    try {
      await api.sendTestNotification();
      setMessage("Test alert sent by the backend.");
      await loadStatus();
    } catch (err: any) {
      setError(getApiErrorMessage(err, "Test alert failed."));
    } finally {
      setTesting(false);
    }
  };

  return (
    <section className="dashboard-page">
      <div className="page-heading">
        <div>
          <h1>Notifications</h1>
          <p>Monitor backend alert channels for Telegram, Slack, and email.</p>
        </div>
      </div>

      {message && <div className="alert alert-success">{message}</div>}
      {error && <div className="alert alert-error">{error}</div>}

      {loading && <p>Loading notification status...</p>}

      {status && (
        <>
          <div className="metric-grid">
            <div className="metric-card">
              <span>Alerts</span>
              <strong>{status.alerts_enabled ? "enabled" : "disabled"}</strong>
              <small>Controlled by backend environment</small>
            </div>
            {(Object.keys(status.channels) as Array<keyof NotificationStatus["channels"]>).map((channel) => (
              <div className="metric-card" key={channel}>
                <span>{channelLabels[channel]}</span>
                <strong>{status.channels[channel] ? "configured" : "not configured"}</strong>
                <small>
                  {channel === "telegram" && status.configured_recipients.telegram_chat
                    ? "Chat ID present"
                    : channel === "email" && status.configured_recipients.email_recipients
                      ? `${status.configured_recipients.email_recipients} recipient(s)`
                      : "Server env required"}
                </small>
              </div>
            ))}
          </div>

          <div className="dashboard-section">
            <div className="section-header">
              <h2>Test Alert</h2>
              <span>{Object.values(status.channels).filter(Boolean).length} channel(s) ready</span>
            </div>
            <button className="primary-action" type="button" onClick={sendTest} disabled={testing}>
              {testing ? "Sending..." : "Send Test Alert"}
            </button>
          </div>
        </>
      )}
    </section>
  );
}
