import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { hasAuthToken } from "../roles";

export type SubscriptionSnapshot = {
  plan_code: string;
  plan_name: string;
  effective_status: string;
  entitlements: string[];
  limits: Record<string, number | null>;
  current_period_end?: string | null;
};

type SubscriptionValue = {
  subscription: SubscriptionSnapshot | null;
  currentPlan: string;
  subscriptionStatus: string;
  expiresAt: string | null;
  entitlements: Set<string>;
  canAccess: (feature: string) => boolean;
  featureLimit: (key: string) => number | null;
  isLoading: boolean;
  error: string | null;
  refreshSubscription: () => Promise<void>;
};

const SubscriptionContext = createContext<SubscriptionValue | null>(null);

export function SubscriptionProvider({ children }: { children: React.ReactNode }) {
  const [subscription, setSubscription] = useState<SubscriptionSnapshot | null>(null);
  const [isLoading, setLoading] = useState(hasAuthToken());
  const [error, setError] = useState<string | null>(null);
  const refreshSubscription = useCallback(async () => {
    if (!hasAuthToken()) { setSubscription(null); setLoading(false); return; }
    setLoading(true);
    try { setSubscription(await api.mySubscription()); setError(null); }
    catch { setSubscription(null); setError("Subscription access could not be verified."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => {
    void refreshSubscription();
    window.addEventListener("quantgrid-role-change", refreshSubscription);
    return () => window.removeEventListener("quantgrid-role-change", refreshSubscription);
  }, [refreshSubscription]);
  const entitlements = useMemo(() => new Set(subscription?.entitlements ?? []), [subscription]);
  const value = useMemo<SubscriptionValue>(() => ({
    subscription, currentPlan: subscription?.plan_name ?? "Unverified", subscriptionStatus: subscription?.effective_status ?? "unknown",
    expiresAt: subscription?.current_period_end ?? null, entitlements, canAccess: (feature) => entitlements.has(feature),
    featureLimit: (key) => subscription?.limits?.[key] ?? null, isLoading, error, refreshSubscription,
  }), [subscription, entitlements, isLoading, error, refreshSubscription]);
  return <SubscriptionContext.Provider value={value}>{children}</SubscriptionContext.Provider>;
}

export function useSubscription() {
  const value = useContext(SubscriptionContext);
  if (!value) throw new Error("useSubscription must be used inside SubscriptionProvider");
  return value;
}

export function useCanAccess(feature: string) { return useSubscription().canAccess(feature); }
export function useFeatureLimit(feature: string) { return useSubscription().featureLimit(feature); }
