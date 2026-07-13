import { render } from "@testing-library/react";
import { axe } from "vitest-axe";
import { describe, expect, it, vi } from "vitest";

vi.mock("../api", () => ({ api: { operationsStatus: vi.fn() } }));
vi.mock("../roles", () => ({ hasAuthToken: () => false }));
vi.mock("../socket", () => ({ createSocket: vi.fn() }));

import { OperationsStatusProvider } from "../context/OperationsStatusContext";
import MarketStatusBanner from "./MarketStatusBanner";

describe("MarketStatusBanner accessibility", () => {
  it("has no detectable accessibility violations", async () => {
    const { container } = render(
      <OperationsStatusProvider><MarketStatusBanner /></OperationsStatusProvider>,
    );
    const results = await axe(container, { rules: { "color-contrast": { enabled: false } } });
    expect(results.violations).toHaveLength(0);
  });
});
