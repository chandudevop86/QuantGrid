import { useEffect, useState } from "react";
import { api } from "../api";
import { getCurrentRole } from "../roles";

type Plan = {
  code: string;
  name: string;
  price_monthly_inr: number;
  description: string;
  features: string[];
};

type SubscriptionSnapshot = {
  user_id: number;
  username: string;
  plan_code: string;
  plan_name: string;
  status: string;
  effective_status: string;
  features: string[];
  price_monthly_inr: number;
  current_period_end?: string | null;
  cancel_at_period_end: boolean;
  provider: string;
};

function money(value: number) {
  return value === 0 ? "Free" : `₹${new Intl.NumberFormat("en-IN").format(value)}/month`;
}

function featureLabel(value: string) {
  return value === "*" ? "All platform features" : value.split("_").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}

export default function Subscription() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [mine, setMine] = useState<SubscriptionSnapshot | null>(null);
  const [accounts, setAccounts] = useState<SubscriptionSnapshot[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const isAdmin = getCurrentRole() === "admin";

  const load = async () => {
    setError(null);
    try {
      const [planPayload, subscription] = await Promise.all([api.subscriptionPlans(), api.mySubscription()]);
      setPlans(planPayload.plans ?? []);
      setMine(subscription);
      if (isAdmin) {
        const adminPayload = await api.adminSubscriptions();
        setAccounts(adminPayload.subscriptions ?? []);
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Subscription information is unavailable.");
    }
  };

  useEffect(() => { void load(); }, []);

  const assign = async (userId: number, planCode: string) => {
    setMessage(null);
    setError(null);
    try {
      await api.assignSubscription(userId, { plan_code: planCode, status: "active", period_days: 30 });
      setMessage("Subscription updated and recorded in the audit trail.");
      await load();
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Subscription update failed.");
    }
  };

  return (
    <section className="dashboard-page">
      <div className="page-heading dashboard-heading">
        <div><span className="page-eyebrow">Account</span><h1>Plan & Access</h1><p>Review your subscription, included capabilities, and renewal status.</p></div>
        <span className={`status-pill ${mine?.effective_status === "active" || mine?.effective_status === "trialing" ? "" : "error"}`}>
          {mine?.effective_status ?? "Loading"}
        </span>
      </div>

      {error && <div className="alert alert-error" role="alert">{typeof error === "string" ? error : "Subscription request failed."}</div>}
      {message && <div className="alert alert-success" role="status">{message}</div>}

      {mine && (
        <div className="metric-grid">
          <article className="metric-card"><span className="metric-label">Current Plan</span><strong className="metric-value">{mine.plan_name}</strong><span className="metric-helper">{money(mine.price_monthly_inr)}</span></article>
          <article className="metric-card"><span className="metric-label">Status</span><strong className="metric-value">{mine.effective_status.toUpperCase()}</strong><span className="metric-helper">Provider: {mine.provider}</span></article>
          <article className="metric-card"><span className="metric-label">Period End</span><strong className="metric-value">{mine.current_period_end ? new Date(mine.current_period_end).toLocaleDateString() : "No expiry"}</strong><span className="metric-helper">{mine.cancel_at_period_end ? "Cancels at period end" : "Access continues"}</span></article>
        </div>
      )}

      <section className="dashboard-section">
        <div className="section-header"><div><h2>Available Plans</h2><span>Prices are product configuration; online billing is not connected yet.</span></div></div>
        <div className="metric-grid">
          {plans.map((plan) => (
            <article className={`metric-card${mine?.plan_code === plan.code ? " metric-card-good" : ""}`} key={plan.code}>
              <span className="metric-label">{plan.name}</span>
              <strong className="metric-value">{money(plan.price_monthly_inr)}</strong>
              <p>{plan.description}</p>
              <span className="metric-helper">{plan.features.map(featureLabel).join(" · ")}</span>
            </article>
          ))}
        </div>
      </section>

      {isAdmin && (
        <section className="dashboard-section">
          <div className="section-header"><div><h2>User Subscriptions</h2><span>Manual assignments are audit logged.</span></div></div>
          <div className="table-wrap"><table className="table"><thead><tr><th>User</th><th>Plan</th><th>Status</th><th>Period End</th><th>Assign</th></tr></thead><tbody>
            {accounts.map((account) => <tr key={account.user_id}><td>{account.username}</td><td>{account.plan_name}</td><td>{account.effective_status}</td><td>{account.current_period_end ? new Date(account.current_period_end).toLocaleDateString() : "No expiry"}</td><td><select aria-label={`Plan for ${account.username}`} value={account.plan_code} onChange={(event) => void assign(account.user_id, event.target.value)}>{plans.map((plan) => <option key={plan.code} value={plan.code}>{plan.name}</option>)}</select></td></tr>)}
          </tbody></table></div>
        </section>
      )}
    </section>
  );
}
