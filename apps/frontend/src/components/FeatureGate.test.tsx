import { render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import FeatureGate from "./FeatureGate";
import RestrictedRoute from "./RestrictedRoute";

const subscription = vi.hoisted(() => ({ canAccess: vi.fn(), isLoading: false, error: null as string | null, currentPlan: "Free", subscriptionStatus: "active" }));
vi.mock("../context/SubscriptionContext", () => ({ useSubscription: () => subscription }));

describe("subscription gates", () => {
  beforeEach(() => { subscription.canAccess.mockReset(); subscription.isLoading = false; subscription.error = null; });

  it("renders permitted content and omits denied feature content", () => {
    subscription.canAccess.mockImplementation((feature: string) => feature === "dashboard.basic");
    const { rerender } = render(<FeatureGate feature="dashboard.basic"><div>Decision</div></FeatureGate>);
    expect(screen.getByText("Decision")).toBeInTheDocument();
    rerender(<FeatureGate feature="options.advanced"><div>Premium values</div></FeatureGate>);
    expect(screen.queryByText("Premium values")).not.toBeInTheDocument();
  });

  it("shows an upgrade state for direct restricted route access", () => {
    subscription.canAccess.mockReturnValue(false);
    render(<BrowserRouter><RestrictedRoute feature="backtest.basic"><div>Backtest payload</div></RestrictedRoute></BrowserRouter>);
    expect(screen.getByText("This page is not included in your plan")).toBeInTheDocument();
    expect(screen.queryByText("Backtest payload")).not.toBeInTheDocument();
  });
});
