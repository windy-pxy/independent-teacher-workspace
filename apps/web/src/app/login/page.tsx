"use client";

import { useRouter } from "next/navigation";
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
        <p className="mt-2 text-sm leading-6 text-[var(--muted)]">教师账户需先通过 README 中的本机命令创建。</p>
        <form className="mt-7 space-y-4" onSubmit={submit}>
          <label><span className="label">账户名</span><input className="field" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required /></label>
          <label><span className="label">密码</span><input className="field" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          {error ? <ErrorNotice error={error} /> : null}
          <button className="button-primary w-full" disabled={pending} type="submit">{pending ? "正在登录…" : "登录"}</button>
        </form>
      </section>
    </main>
  );
}
