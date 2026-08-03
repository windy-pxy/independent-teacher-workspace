import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, jsonBody } from "./api";

describe("API client", () => {
  afterEach(() => {
    document.cookie = "teacher_workspace_session_csrf=; Max-Age=0; path=/";
    vi.restoreAllMocks();
  });

  it("uses the same-origin API prefix and sends CSRF on writes", async () => {
    document.cookie = "teacher_workspace_session_csrf=test%20csrf; path=/";
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: "student-1" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await api("/students", { method: "POST", ...jsonBody({ display_name: "虚构学生甲" }) });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/students",
      expect.objectContaining({ credentials: "include", cache: "no-store" }),
    );
    const request = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(new Headers(request.headers).get("X-CSRF-Token")).toBe("test csrf");
    expect(new Headers(request.headers).get("Content-Type")).toBe("application/json");
  });

  it("preserves the backend error code without exposing response internals", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        json: async () => ({ code: "VERSION_CONFLICT", message: "记录已被修改" }),
      }),
    );

    await expect(api("/students/student-1")).rejects.toEqual(
      new ApiError("记录已被修改", 409, "VERSION_CONFLICT"),
    );
  });
});
