"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader, ErrorNotice } from "@/components/page-ui";
import { api, apiBlob, jsonBody } from "@/lib/api";
import { clearSessionCache } from "@/lib/session-cache";
import { broadcastAuthChanged, clearTabUserId } from "@/lib/account-context";
import type { AuthUser } from "@/lib/types";

type Session = { id: string; created_at: string; expires_at: string; is_current: boolean };
type StorageUsage = { used_bytes: number; quota_bytes: number; remaining_bytes: number };

function formatBytes(value: number) {
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 1 }).format(value / 1024 / 1024);
}

export default function AccountPage() {
  const client = useQueryClient();
  const account = useQuery({ queryKey: ["auth", "me"], queryFn: () => api<AuthUser>("/auth/me") });
  const sessions = useQuery({ queryKey: ["account-sessions"], queryFn: () => api<Session[]>("/auth/sessions") });
  const storage = useQuery({ queryKey: ["storage-usage"], queryFn: () => api<StorageUsage>("/auth/storage-usage") });
  const [error, setError] = useState<unknown>();
  const [message, setMessage] = useState("");
  const [code, setCode] = useState("");
  const [codeSaved, setCodeSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!code || codeSaved) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [code, codeSaved]);

  async function change(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    if (values.get("password") !== values.get("confirmation")) { setError(new Error("两次新密码不一致")); return; }
    setBusy(true); setError(undefined);
    try {
      await api<void>("/auth/password", { method: "POST", ...jsonBody({ current_password: values.get("current"), new_password: values.get("password") }) });
      clearTabUserId();
      broadcastAuthChanged();
      await clearSessionCache(client);
      window.location.replace("/login");
    } catch (caught) { setError(caught); } finally { setBusy(false); }
  }
  async function recovery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setBusy(true); setError(undefined); setCode("");
    try {
      const result = await api<{ recovery_code: string }>("/auth/recovery-code", { method: "POST", ...jsonBody({ current_password: new FormData(form).get("current") }) });
      setCode(result.recovery_code); setCodeSaved(false); form.reset();
    } catch (caught) { setError(caught); } finally { setBusy(false); }
  }
  async function revoke() {
    setBusy(true); setError(undefined);
    try {
      await api<void>("/auth/sessions/revoke-others", { method: "POST" });
      await client.invalidateQueries({ queryKey: ["account-sessions"] });
      setMessage("其他设备已退出，当前登录保持有效。");
    } catch (caught) { setError(caught); } finally { setBusy(false); }
  }
  async function exportData() {
    setBusy(true); setError(undefined); setMessage("");
    try {
      const result = await apiBlob("/auth/data-export.zip", { method: "POST" });
      const url = URL.createObjectURL(result.blob);
      const anchor = document.createElement("a");
      anchor.href = url; anchor.download = result.filename; anchor.click();
      URL.revokeObjectURL(url);
      setMessage("账户资料导出已开始下载，请妥善保管压缩包。");
    } catch (caught) { setError(caught); } finally { setBusy(false); }
  }
  async function requestDeletion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    setBusy(true); setError(undefined); setMessage("");
    try {
      await api<{ scheduled_for: string }>("/auth/deletion-request", {
        method: "POST",
        ...jsonBody({
          current_password: values.get("current"),
          confirm_username: values.get("username"),
        }),
      });
      await client.invalidateQueries({ queryKey: ["auth", "me"] });
      await client.invalidateQueries({ queryKey: ["account-sessions"] });
      form.reset();
      setMessage("账户删除申请已提交。撤销期内可在本页取消；到期后资料将永久删除。");
    } catch (caught) { setError(caught); } finally { setBusy(false); }
  }
  async function cancelDeletion() {
    setBusy(true); setError(undefined); setMessage("");
    try {
      await api<void>("/auth/deletion-cancel", { method: "POST" });
      await client.invalidateQueries({ queryKey: ["auth", "me"] });
      setMessage("账户删除申请已取消，资料会继续保留。");
    } catch (caught) { setError(caught); } finally { setBusy(false); }
  }
  return <>
    <PageHeader title="账户安全" description="管理密码、恢复码和登录会话。退出登录不会删除已保存的教学资料。" />
    {error ? <ErrorNotice error={error} /> : null}
    {message ? <p role="status">{message}</p> : null}
    <div className="grid gap-5 lg:grid-cols-2">
      <section className="card"><h2 className="text-xl font-semibold">修改密码</h2><p className="my-3 text-sm">修改后包括当前设备在内的所有设备需重新登录。</p>
        <form className="grid gap-4" onSubmit={change}>
          <label><span className="label">当前密码</span><input className="field" name="current" type="password" autoComplete="current-password" maxLength={200} required /></label>
          <label><span className="label">新密码（12–200 个字符）</span><input className="field" name="password" type="password" autoComplete="new-password" minLength={12} maxLength={200} required /></label>
          <label><span className="label">确认新密码</span><input className="field" name="confirmation" type="password" autoComplete="new-password" minLength={12} maxLength={200} required /></label>
          <button className="button-primary" disabled={busy}>修改并重新登录</button>
        </form>
      </section>
      <section className="card"><h2 className="text-xl font-semibold">账户恢复码</h2><p className="my-3 text-sm leading-7">用于忘记密码时找回账户。生成后旧码立即失效，新码只展示一次，请保存在密码管理器中。</p>
        <form className="grid gap-4" onSubmit={recovery}>
          <label><span className="label">验证当前密码</span><input className="field" name="current" type="password" autoComplete="current-password" maxLength={200} required /></label>
          <button className="button-secondary" disabled={busy || Boolean(code && !codeSaved)}>生成新的恢复码</button>
        </form>
        {code ? <div className="mt-4 space-y-3"><label className="block"><span className="label">请立即保存新恢复码</span><input className="field font-mono" readOnly value={code} onFocus={e => e.target.select()} /></label><label className="flex items-center gap-2"><input type="checkbox" checked={codeSaved} onChange={e => setCodeSaved(e.target.checked)} />我已安全保存新恢复码</label></div> : null}
      </section>
      <section className="card lg:col-span-2"><h2 className="text-xl font-semibold">有效登录会话</h2>
        {sessions.error ? <ErrorNotice error={sessions.error} /> : sessions.isPending ? <p>正在读取…</p> : <ul className="my-4 space-y-2">{sessions.data?.map(item => <li key={item.id}>{item.is_current ? "当前设备" : "其他登录会话"} · 登录时间 {new Date(item.created_at).toLocaleString("zh-CN")}</li>)}</ul>}
        <button className="button-secondary" disabled={busy || !sessions.data?.some(item => !item.is_current)} onClick={revoke}>退出其他所有会话</button>
      </section>
      <section className="card lg:col-span-2"><h2 className="text-xl font-semibold">数据与隐私</h2>
        <p className="my-3 text-sm leading-7">下载当前账户的结构化记录、上传附件和已生成文档。压缩包可能包含学生隐私，请只保存在你控制的加密设备中。</p>
        {storage.data ? <p className="mb-3 text-sm">上传空间已使用 <strong>{formatBytes(storage.data.used_bytes)} MB</strong> / {formatBytes(storage.data.quota_bytes)} MB，剩余 {formatBytes(storage.data.remaining_bytes)} MB。归档资料仍占用空间。</p> : null}
        <div className="flex flex-wrap gap-3"><button className="button-primary" type="button" disabled={busy} onClick={exportData}>导出我的全部资料</button><Link className="button-secondary" href="/privacy" target="_blank">查看隐私说明</Link></div>
      </section>
      <section className="card border border-red-200 lg:col-span-2">
        <h2 className="text-xl font-semibold text-red-900">删除账户与全部资料</h2>
        {account.isPending ? <p className="my-3">正在读取账户状态…</p> : account.error ? <ErrorNotice error={account.error} /> : account.data?.deletion_scheduled_for ? <div className="mt-3 space-y-4">
          <p className="leading-7">删除申请已生效，预计在 <strong>{new Date(account.data.deletion_scheduled_for).toLocaleString("zh-CN")}</strong> 后永久清除。撤销期内仍可导出资料或取消申请。</p>
          <button className="button-secondary" type="button" disabled={busy} onClick={cancelDeletion}>取消删除，继续保留账户</button>
        </div> : <>
          <p className="my-3 text-sm leading-7">建议先点击上方“导出我的全部资料”。提交后，其他设备会立即退出；当前设备可在撤销期内取消。到期清除后无法恢复。</p>
          <form className="grid gap-4 md:max-w-xl" onSubmit={requestDeletion}>
            <label><span className="label">输入账户名 <strong>{account.data?.username}</strong> 确认</span><input className="field" name="username" autoComplete="username" required /></label>
            <label><span className="label">验证当前密码</span><input className="field" name="current" type="password" autoComplete="current-password" maxLength={200} required /></label>
            <button className="button-secondary border-red-300 text-red-900" disabled={busy}>申请删除账户</button>
          </form>
        </>}
      </section>
    </div>
  </>;
}
