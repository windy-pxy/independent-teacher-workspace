"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { api } from "@/lib/api";
import type { AuthUser } from "@/lib/types";

const navigation = [
  ["/", "仪表盘"],
  ["/students", "学生档案"],
  ["/subjects", "学科"],
  ["/plans", "教学计划"],
  ["/lessons", "课程与课表"],
  ["/lesson-plans", "AI 教案"],
  ["/materials", "资料库"],
  ["/feedback", "课后反馈"],
  ["/wrong-questions", "错题与复习"],
  ["/practice", "针对性练习"],
  ["/billing", "课时与收费"],
  ["/settings/ai", "模板与 AI"],
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const session = useQuery({ queryKey: ["auth", "me"], queryFn: () => api<AuthUser>("/auth/me") });

  useEffect(() => {
    if (session.error) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [pathname, router, session.error]);

  if (session.isPending) return <main className="grid min-h-screen place-items-center">正在验证登录状态…</main>;
  if (session.error) return <main className="grid min-h-screen place-items-center">正在前往登录页…</main>;

  async function logout() {
    await api<void>("/auth/logout", { method: "POST" });
    router.replace("/login");
    router.refresh();
  }

  return (
    <div className="min-h-screen bg-[var(--background)] text-[var(--foreground)]">
      <header className="sticky top-0 z-20 border-b border-[var(--border)] bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-4">
          <Link href="/" className="font-semibold tracking-tight">独立教师工作台</Link>
          <div className="flex items-center gap-3 text-sm text-[var(--muted)]">
            <span>{session.data?.username}</span>
            <button className="button-secondary" type="button" onClick={logout}>退出</button>
          </div>
        </div>
      </header>
      <div className="mx-auto grid max-w-7xl gap-6 px-5 py-6 md:grid-cols-[190px_minmax(0,1fr)]">
        <nav
          aria-label="主导航"
          className="flex gap-2 overflow-x-auto md:sticky md:top-24 md:max-h-[calc(100vh-7rem)] md:flex-col md:self-start md:overflow-x-visible md:overflow-y-auto"
        >
          {navigation.map(([href, label]) => (
            <Link
              key={href}
              href={href}
              className={`nav-link ${pathname === href ? "nav-link-active" : ""}`}
            >
              {label}
            </Link>
          ))}
        </nav>
        <main className="min-w-0">{children}</main>
      </div>
    </div>
  );
}
