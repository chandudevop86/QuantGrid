import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { axe } from "vitest-axe";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ subscriptionPlans: vi.fn(), register: vi.fn() }));
vi.mock("../api", () => ({ api }));

import PublicPlans from "./PublicPlans";
import Signup from "./Signup";

describe("public access flows", () => {
  beforeEach(() => {
    api.subscriptionPlans.mockReset();
    api.register.mockReset();
  });

  it("renders API-backed plans accessibly without inventing prices", async () => {
    api.subscriptionPlans.mockResolvedValue({ plans: [{ code: "free", name: "Free", description: "Decision support", price_monthly_inr: 0, entitlements: ["dashboard.basic"], limits: {} }] });
    const { container } = render(<MemoryRouter><PublicPlans /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Choose the access you need." })).toBeVisible();
    expect(await screen.findByText("Free", { selector: "strong" })).toBeVisible();
    expect((await axe(container, { rules: { "color-contrast": { enabled: false } } })).violations).toHaveLength(0);
  });

  it("keeps registration client-side when password confirmation fails", async () => {
    const { container } = render(<MemoryRouter><Signup /></MemoryRouter>);
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "new-user" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "StrongPass1!" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "DifferentPass1!" } });
    fireEvent.click(screen.getByRole("button", { name: "Create free account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Passwords do not match.");
    expect(api.register).not.toHaveBeenCalled();
    await waitFor(async () => expect((await axe(container, { rules: { "color-contrast": { enabled: false } } })).violations).toHaveLength(0));
  });
});
