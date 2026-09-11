import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AccountEntry } from "./account-entry";

vi.mock("@/lib/api", () => ({ api: vi.fn(), jsonBody: (value: unknown) => ({ body: JSON.stringify(value) }) }));
import { api } from "@/lib/api";

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("新教师注册", () => {
  it("注册关闭时说明原因并提供返回登录入口", async () => {
    vi.mocked(api).mockResolvedValue({ enabled: false });
    render(<AccountEntry mode="register" />);
    expect(await screen.findByText(/当前暂未开放注册/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "返回登录" })).toHaveAttribute("href", "/login");
    expect(screen.queryByRole("button", { name: "注册教师账户" })).not.toBeInTheDocument();
  });
  it("先纠正密码不一致，注册成功必须保存恢复码才能继续", async () => {
    vi.mocked(api).mockImplementation(async path => path === "/auth/registration" ? { enabled: true } : { recovery_code: "fictional-recovery-code-not-real" });
    render(<AccountEntry mode="register" />);
    const submit = await screen.findByRole("button", { name: "注册教师账户" });
    fireEvent.change(screen.getByLabelText(/账户名/), { target: { value: "fictional-teacher" } });
    fireEvent.change(screen.getByLabelText(/^密码/), { target: { value: "fictional-password" } });
    fireEvent.change(screen.getByLabelText("再次输入密码"), { target: { value: "fictional-mismatch" } });
    fireEvent.click(submit);
    expect(await screen.findByRole("alert")).toHaveTextContent("两次密码不一致");
    expect(vi.mocked(api).mock.calls.filter(([path]) => path === "/auth/register")).toHaveLength(0);
    fireEvent.change(screen.getByLabelText("再次输入密码"), { target: { value: "fictional-password" } });
    fireEvent.click(submit);
    await waitFor(() => expect(screen.getByText(/注册成功/)).toBeInTheDocument());
    expect(screen.queryByRole("link", { name: "前往登录" })).not.toBeInTheDocument();
    expect(screen.getByText("账户名：fictional-teacher")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox"));
    expect(screen.getByRole("link", { name: "前往登录" })).toHaveAttribute("href", "/login");
  });
});
