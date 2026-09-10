import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppShell } from "./app-shell";

vi.mock("next/navigation", () => ({
  usePathname: () => "/students",
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }),
}));
vi.mock("@/lib/api", () => ({ api: vi.fn() }));

import { api } from "@/lib/api";

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("不熟悉网站的教师退出操作", () => {
  it("断网退出失败时给出可见反馈，并保留重试入口和已加载页面", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    vi.mocked(api).mockImplementation(async (path) => {
      if (path === "/auth/me") return { id: "fictional-teacher", username: "虚构教师" };
      throw new Error("连接失败，请重试");
    });
    render(
      <QueryClientProvider client={client}>
        <AppShell><p>虚构学生档案</p></AppShell>
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: /退出/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("连接失败，请重试");
    expect(screen.getByText("虚构学生档案")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /退出/ }));
    await waitFor(() => expect(vi.mocked(api).mock.calls.filter(([path]) => path === "/auth/logout")).toHaveLength(2));
    await screen.findByRole("alert");
    client.clear();
  });
});
