import { useSubscription } from "../context/SubscriptionContext";
import StatusBadge from "./StatusBadge";

export default function SubscriptionBadge() {
  const { currentPlan, subscriptionStatus } = useSubscription();
  const tone = subscriptionStatus === "active" ? "positive" : subscriptionStatus === "trialing" ? "warning" : "danger";
  return <StatusBadge tone={tone}>{currentPlan}</StatusBadge>;
}
