"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { ErrorNotice } from "@/components/page-ui";
import { api, jsonBody } from "@/lib/api";
import { broadcastAuthChanged, clearTabUserId } from "@/lib/account-context";

export function AccountEntry({ mode }: { mode: "register" | "recover" }) {
  const [enabled, setEnabled] = useState<boolean>();
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState("");
  const [registeredName, setRegisteredName] = useState("");
  const [saved, setSaved] = useState(false);
  const [done, setDone] = useState(false);
  useEffect(() => {
    if (mode === "register") api<{ enabled: boolean }>("/auth/registration")
      .then(value => setEnabled(value.enabled)).catch(setError);
  }, [mode]);
  useEffect(() => {
    if (!code || saved) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [code, saved]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const username = String(values.get("username") ?? "").trim();
    const password = String(values.get("password") ?? "");
    if (password !== values.get("confirmation")) { setError(new Error("两次密码不一致，请重新确认")); return; }
    if (!password.trim()) { setError(new Error("密码不能全部为空格")); return; }
    setBusy(true); setError(undefined);
    try {
      if (mode === "register") {
        const response = await api<{ recovery_code: string }>("/auth/register", {
          method: "POST", ...jsonBody({ username, password, password_confirmation: password }),
        });
        setRegisteredName(username);
        setCode(response.recovery_code);
      } else {
        await api<void>("/auth/reset-password", { method: "POST", ...jsonBody({
          username, new_password: password, recovery_code: String(values.get("recovery_code") ?? "").trim(),
        }) });
        clearTabUserId();
        broadcastAuthChanged();
        setDone(true);
      }
    } catch (caught) { setError(caught); } finally { setBusy(false); }
  }

  return <main className="grid min-h-screen place-items-center px-5 py-12">
    <section className="card w-full max-w-lg p-8">
      <h1 className="page-title">{mode === "register" ? "创建教师账户" : "找回账户"}</h1>
      <p className="mt-3 text-sm leading-7 text-[var(--muted)]">{mode === "register"
        ? "每位教师拥有独立资料。已保存的学生与课程会保留，退出后重新登录即可继续。新账户暂未开通 AI 生成。"
        : "使用创建账户时保存的恢复码重设密码。成功后所有设备需要重新登录，旧恢复码随即失效。"}</p>
      {error ? <ErrorNotice error={error} /> : null}
      {code ? <div className="mt-6 space-y-4" role="status">
        <h2 className="font-semibold">注册成功，请先保存恢复码</h2>
        <p>账户名：{registeredName}</p>
        <p className="text-sm leading-7">恢复码仅展示这一次，请存入密码管理器。它可以重置账户密码，不要分享给他人。</p>
        <label><span className="label">恢复码</span><input className="field font-mono" readOnly value={code} onFocus={e => e.target.select()} /></label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={saved} onChange={e => setSaved(e.target.checked)} />我已保存账户名、密码和恢复码</label>
        {saved ? <Link className="button-primary" href="/login">前往登录</Link> : <p className="text-sm">保存并勾选后可继续登录。</p>}
      </div> : done ? <div className="mt-6 space-y-4" role="status"><p>密码已重置。登录后请在“账户安全”生成新的恢复码。</p><Link className="button-primary" href="/login">使用新密码登录</Link></div>
        : mode === "register" && enabled !== true ? <p className="my-6" role="status">{enabled === false ? "当前暂未开放注册，请稍后再来。" : "正在确认注册是否开放…"}</p>
        : <form className="mt-6 grid gap-4" onSubmit={submit}>
          <label><span className="label">账户名</span><input className="field" name="username" autoComplete="username" required maxLength={mode === "register" ? 40 : 100} pattern={mode === "register" ? "[a-z][a-z0-9_\\-]{2,39}" : undefined} />{mode === "register" ? <span className="text-xs">3–40 位，以小写字母开头，可含数字、下划线和短横线。</span> : null}</label>
          {mode === "recover" ? <label><span className="label">恢复码</span><input className="field" name="recovery_code" autoComplete="off" required minLength={20} maxLength={128} /></label> : null}
          <label><span className="label">{mode === "recover" ? "新密码" : "密码"}（12–200 个字符）</span><input className="field" name="password" type="password" autoComplete="new-password" required minLength={12} maxLength={200} /></label>
          <label><span className="label">再次输入密码</span><input className="field" name="confirmation" type="password" autoComplete="new-password" required minLength={12} maxLength={200} /></label>
          <button className="button-primary w-full" disabled={busy}>{busy ? "正在处理…" : mode === "register" ? "注册教师账户" : "重设密码"}</button>
        </form>}
      {!code && !done ? <Link className="mt-6 inline-block underline" href="/login">返回登录</Link> : null}
    </section>
  </main>;
}
