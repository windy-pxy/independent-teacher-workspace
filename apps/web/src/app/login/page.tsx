"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";

import { ErrorNotice } from "@/components/page-ui";
import { api, jsonBody } from "@/lib/api";
import { clearSessionCache } from "@/lib/session-cache";

export default function LoginPage() {
  const router = useRouter();
  const client = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>();
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(undefined);
    try {
      await api("/auth/login", {
        method: "POST",
        ...jsonBody({ username, password }),
      });
      await clearSessionCache(client);
      router.replace("/");
      router.refresh();
    } catch (caught) {
      setError(caught);
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center px-5 py-12">
      <section className="card w-full max-w-md p-8">
        <p className="text-sm font-semibold tracking-[0.2em] text-[var(--accent)]">TEACHER ONLY</p>
        <h1 className="mt-3 text-3xl font-semibold">登录工作台</h1>
        <p className="mt-2 text-sm leading-6 text-[var(--muted)]">登录自己的教师账户，继续管理已保存的学生、课程和教学资料。</p>
        <form className="mt-7 grid gap-4" onSubmit={submit}>
          <label><span className="label">账户名</span><input className="field" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required /></label>
          <label><span className="label">密码</span><input className="field" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          {error ? <ErrorNotice error={error} /> : null}
          <button className="button-primary w-full" disabled={pending} type="submit">{pending ? "正在登录…" : "登录"}</button>
        </form>
        <div className="mt-5 flex justify-between gap-4 text-sm"><Link href="/register" className="underline">创建教师账户</Link><Link href="/recover" className="underline">忘记密码？</Link></div>
      </section>
    </main>
  );
}
