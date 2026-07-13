import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  operationsStatus: vi.fn(),
  socket: {
    onopen: null as null | (() => void),
    onmessage: null as null | ((event: MessageEvent) => void),
    onerror: null as null | (() => void),
    onclose: null as null | (() => void),
    close: vi.fn(),
  },
}));

vi.mock("../api", () => ({ api: { operationsStatus: mocks.operationsStatus } }));
vi.mock("../roles", () => ({ hasAuthToken: () => true }));
vi.mock("../socket", () => ({ createSocket: () => mocks.socket }));

import { OperationsStatusProvider, useOperationsStatus } from "./OperationsStatusContext";

describe("OperationsStatusProvider", () => {
  beforeEach(() => {
    mocks.operationsStatus.mockReset();
    mocks.socket.close.mockReset();
    mocks.socket.onopen = null;
    mocks.socket.onmessage = null;
    mocks.socket.onerror = null;
    mocks.socket.onclose = null;
  });

  it("loads one shared status and accepts WebSocket updates", async () => {
    mocks.operationsStatus.mockResolvedValue({ updated_at: "initial", market_status: { state: "closed" } });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <OperationsStatusProvider>{children}</OperationsStatusProvider>
    );
    const { result } = renderHook(() => useOperationsStatus(), { wrapper });

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(mocks.operationsStatus).toHaveBeenCalledTimes(1);
    expect(result.current.operations.updated_at).toBe("initial");

    act(() => mocks.socket.onmessage?.({
      data: JSON.stringify({ type: "dashboard_status", payload: { updated_at: "socket" } }),
    } as MessageEvent));
    expect(result.current.operations.updated_at).toBe("socket");
  });
});
