import type { ReactNode } from "react";
import LoadingSkeleton from "./LoadingSkeleton";
import UpgradePrompt from "./UpgradePrompt";
import { useSubscription } from "../context/SubscriptionContext";

export default function RestrictedRoute({ feature, children }: { feature: string; children: ReactNode }) {
  const { canAccess, isLoading, error, isSubscriptionExempt } = useSubscription();
  if (isLoading) return <LoadingSkeleton />;
  if ((!isSubscriptionExempt && error) || !canAccess(feature)) return <UpgradePrompt feature={feature} title={error ? "Access could not be verified" : "This page is not included in your plan"} />;
  return children;
}
