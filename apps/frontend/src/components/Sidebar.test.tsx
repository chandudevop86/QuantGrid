import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

vi.mock("../roles", () => ({ canAccessRoute: () => true, getCurrentRole: () => "admin", hasAuthToken: () => true }));
vi.mock("../context/SubscriptionContext", () => ({ useSubscription: () => ({ canAccess: (feature: string) => feature !== "admin.broker", isLoading: false }) }));

import Sidebar from "./Sidebar";

describe("responsive subscription navigation", () => {
  it("omits denied links and exposes keyboard-operable mobile navigation", () => {
    render(<MemoryRouter><Sidebar collapsed={false} onNavigate={vi.fn()} /></MemoryRouter>);
    expect(screen.queryByRole("link", { name: "Broker setup" })).not.toBeInTheDocument();
    const more = screen.getByRole("button", { name: "More" });
    expect(more).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(more);
    expect(more).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("navigation", { name: "More navigation" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Close navigation" }));
    expect(screen.queryByRole("navigation", { name: "More navigation" })).not.toBeInTheDocument();
  });
});
