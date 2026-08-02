import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HealthPanel } from "./health-panel";

describe("HealthPanel", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("shows the ready state returned by the backend", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: "ok", service: "api", database: "ok" }),
    }));

    render(<HealthPanel />);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("连接正常"));
  });

  it("shows a useful failure message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<HealthPanel />);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("尚未就绪"));
  });
});
