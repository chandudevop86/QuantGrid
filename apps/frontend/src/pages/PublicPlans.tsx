import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import ErrorState from "../components/ErrorState";
import LoadingSkeleton from "../components/LoadingSkeleton";

type PublicPlan = {
  code: string;
  name: string;
  description: string;
  price_monthly_inr: number;
  entitlements: string[];
  limits: Record<string, number | null>;
};

const highlights: Record<string, string[]> = {
  free: ["Current market decision", "Basic support and resistance", "Latest 5 signals", "Manual paper trading"],
  basic: ["Live market data", "Full key levels and checklist", "VWAP and volume", "Latest 25 signals"],
  pro: ["Option-chain analytics", "Backtesting", "Advanced risk and alerts", "Paper-trading automation"],
  premium: ["Institutional and smart-money analysis", "Advanced portfolio analytics", "Full exports", "API access"],
};

function price(plan: PublicPlan) {
  return plan.price_monthly_inr === 0 ? "Free" : `₹${new Intl.NumberFormat("en-IN").format(plan.price_monthly_inr)}/month`;
}

export default function PublicPlans() {
  const [plans, setPlans] = useState<PublicPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = async () => {
    setLoading(true); setError(null);
    try { setPlans((await api.subscriptionPlans()).plans ?? []); }
    catch { setError("Plans are temporarily unavailable."); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, []);

  return <section className="qg-public-plans" aria-labelledby="plans-title">
    <header><span className="qg-card-label">Plans and access</span><h1 id="plans-title">Choose the access you need.</h1><p>Start in paper mode and upgrade only when you need deeper analysis. Live trading always requires separate approval.</p></header>
    {loading && <LoadingSkeleton />}
    {!loading && error && <ErrorState message={error} onRetry={() => void load()} />}
    {!loading && !error && <div className="qg-plan-grid">{plans.map((plan) => <article className={`qg-card qg-public-plan${plan.code === "pro" ? " featured" : ""}`} key={plan.code}>
      <div><span>{plan.name}</span>{plan.code === "pro" && <small>Most capable</small>}</div>
      <strong>{price(plan)}</strong><p>{plan.description}</p>
      <ul>{(highlights[plan.code] ?? plan.entitlements.slice(0, 4)).map((feature) => <li key={feature}>✓ {feature}</li>)}</ul>
      <Link to="/" state={{ plan: plan.code }}>Sign in to choose {plan.name}</Link>
    </article>)}</div>}
    <aside>Billing is not connected yet. Signing in does not create a charge or activate a paid plan.</aside>
  </section>;
}
