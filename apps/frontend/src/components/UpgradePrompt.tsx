import { Link } from "react-router-dom";
import { useSubscription } from "../context/SubscriptionContext";

export default function UpgradePrompt({ feature, title = "Upgrade required" }: { feature: string; title?: string }) {
  const { currentPlan, subscriptionStatus } = useSubscription();
  return <section className="qg-state-panel qg-upgrade-prompt" role="status" aria-labelledby="upgrade-title">
    <span className="qg-card-label">Plan access</span><h2 id="upgrade-title">{title}</h2>
    <p><strong>{currentPlan}</strong> ({subscriptionStatus}) does not include {feature.replace(/\./g, " ")}.</p>
    <Link to="/subscription">Review plans</Link>
  </section>;
}
