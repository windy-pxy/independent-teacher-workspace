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

afterEach(() => { cleanup(); window.sessionStorage.clear(); vi.clearAllMocks(); });

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

  it("其他标签页换号后立即阻止继续编辑，并说明如何安全恢复", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    vi.mocked(api).mockResolvedValue({ id: "fictional-teacher", username: "虚构教师" });
    render(
      <QueryClientProvider client={client}>
        <AppShell><p>尚未保存的虚构资料</p></AppShell>
      </QueryClientProvider>,
    );
    await screen.findByText("尚未保存的虚构资料");
    window.dispatchEvent(new Event("teacher-workspace:context-mismatch"));

    expect(await screen.findByRole("alert")).toHaveTextContent("另一个标签页更改了登录状态");
    expect(screen.getByText(/本页已经停止提交/)).toBeInTheDocument();
    expect(screen.queryByText("尚未保存的虚构资料")).not.toBeInTheDocument();
    client.clear();
  });
});
