"use client";

import {
  Books,
  CalendarBlank,
  ChalkboardTeacher,
  Exam,
  Export,
  FolderOpen,
  GearSix,
  MagicWand,
  NotePencil,
  SignOut,
  SquaresFour,
  Target,
  TreeStructure,
  UsersThree,
  Wallet,
} from "@phosphor-icons/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { AuthUser } from "@/lib/types";
import { clearSessionCache } from "@/lib/session-cache";
import { ErrorNotice } from "@/components/page-ui";

const navigation = [
  {
    label: "日常工作",
    items: [
      { href: "/", label: "仪表盘", icon: SquaresFour },
      { href: "/lessons", label: "课程与课表", icon: CalendarBlank },
      { href: "/lesson-plans", label: "AI 教案", icon: MagicWand },
      { href: "/feedback", label: "课后反馈", icon: NotePencil },
    ],
  },
  {
    label: "教学档案",
    items: [
      { href: "/students", label: "学生档案", icon: UsersThree },
      { href: "/subjects", label: "学科", icon: Books },
      { href: "/plans", label: "教学计划", icon: TreeStructure },
      { href: "/wrong-questions", label: "错题与复习", icon: Exam },
      { href: "/practice", label: "针对性练习", icon: Target },
    ],
  },
  {
    label: "资料与管理",
    items: [
      { href: "/materials", label: "资料库", icon: FolderOpen },
      { href: "/exports", label: "导出与 Obsidian", icon: Export },
      { href: "/billing", label: "课时与收费", icon: Wallet },
      { href: "/settings/ai", label: "模板与 AI", icon: GearSix },
      { href: "/account", label: "账户安全", icon: GearSix },
    ],
  },
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const client = useQueryClient();
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<unknown>();
  const session = useQuery({ queryKey: ["auth", "me"], queryFn: () => api<AuthUser>("/auth/me") });

  useEffect(() => {
    if (session.error) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [pathname, router, session.error]);

  if (session.isPending) return <main className="grid min-h-screen place-items-center">正在验证登录状态…</main>;
  if (session.error) return <main className="grid min-h-screen place-items-center">正在前往登录页…</main>;

  async function logout() {
    setLoggingOut(true);
    setLogoutError(undefined);
    try {
      await api<void>("/auth/logout", { method: "POST" });
      await clearSessionCache(client);
      window.location.replace("/login");
    } catch (caught) {
      setLogoutError(caught);
      setLoggingOut(false);
    }
  }

  if (loggingOut) return <main className="grid min-h-screen place-items-center" role="status">正在退出登录…</main>;

  return (
    <div className="workspace-shell">
      <header className="workspace-header">
        <div className="workspace-header-inner">
          <Link href="/" className="brand-lockup" aria-label="独立教师工作台首页">
            <span className="brand-seal"><ChalkboardTeacher size={20} weight="duotone" /></span>
            <span>
              <span className="brand-title block">独立教师工作台</span>
              <span className="brand-subtitle block">专注备课 · 用心教学</span>
            </span>
          </Link>
          <div className="workspace-user">
            <span>{session.data?.username}</span>
            <span className="workspace-avatar" aria-hidden="true">师</span>
            <button className="button-secondary" type="button" onClick={logout}>
              <SignOut size={17} />
              <span className="hidden sm:inline">退出</span>
            </button>
          </div>
        </div>
      </header>
      <div className="workspace-body">
        <nav aria-label="主导航" className="workspace-sidebar">
          {navigation.map((group) => (
            <div className="nav-group" key={group.label}>
              <p className="nav-group-label">{group.label}</p>
              {group.items.map((item) => {
                const active = pathname === item.href;
                const Icon = item.icon;
                return (
                  <Link key={item.href} href={item.href} className={`nav-link ${active ? "nav-link-active" : ""}`} aria-current={active ? "page" : undefined}>
                    <Icon size={18} weight={active ? "fill" : "regular"} />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
        <main className="workspace-main">{logoutError ? <ErrorNotice error={logoutError} /> : null}{children}</main>
      </div>
    </div>
  );
}
