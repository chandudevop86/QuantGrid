import type { ReactNode } from "react";
import { useSubscription } from "../context/SubscriptionContext";

export default function FeatureGate({ feature, children, fallback = null }: { feature: string; children: ReactNode; fallback?: ReactNode }) {
  const { canAccess, isLoading } = useSubscription();
  if (isLoading) return null;
  return canAccess(feature) ? children : fallback;
}
