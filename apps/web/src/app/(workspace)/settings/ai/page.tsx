"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";

import { EmptyState, ErrorNotice, PageHeader } from "@/components/page-ui";
import { api, jsonBody } from "@/lib/api";
import type { AISettings, AIUsage, PromptTemplate } from "@/lib/types";

export default function AISettingsPage() {
  const client = useQueryClient();
  const settings = useQuery({
    queryKey: ["ai-settings"],
    queryFn: () => api<AISettings>("/ai-settings"),
  });
  const templates = useQuery({
    queryKey: ["prompt-templates"],
    queryFn: () => api<PromptTemplate[]>("/prompt-templates"),
  });
  const usage = useQuery({ queryKey: ["ai-usage"], queryFn: () => api<AIUsage>("/ai-usage") });
  const [selectedId, setSelectedId] = useState<string>();
  const selected =
    templates.data?.find((template) => template.id === selectedId) ??
    templates.data?.[0];
  const [error, setError] = useState<unknown>();

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = new FormData(event.currentTarget);
    try {
      await api(`/prompt-templates/${selected.id}`, {
        method: "PUT",
        ...jsonBody({
          name: String(form.get("name")),
          system_prompt: String(form.get("system_prompt")),
          user_prompt_template: String(form.get("user_prompt_template")),
          change_reason: String(form.get("change_reason")),
          current_version_number: selected.current_version_number,
        }),
      });
      await client.invalidateQueries({ queryKey: ["prompt-templates"] });
    } catch (caught) {
      setError(caught);
    }
  }

  return (
    <>
      <PageHeader
        title="模板与 AI"
        description="提示词按逻辑键和不可变版本集中管理；模型名称和密钥只从服务端环境变量读取。"
      />
      {error ? <ErrorNotice error={error} /> : null}
      <section className="card mt-4">
        <h2 className="font-semibold">当前运行方式</h2>
        {settings.data ? (
          <dl className="mt-3 grid gap-3 text-sm md:grid-cols-3">
            <div><dt className="text-[var(--muted)]">提供商</dt><dd className="mt-1 font-medium">{settings.data.provider}</dd></div>
            <div><dt className="text-[var(--muted)]">模型</dt><dd className="mt-1 font-medium">{settings.data.model ?? "未配置（Mock 不需要）"}</dd></div>
            <div><dt className="text-[var(--muted)]">真实调用</dt><dd className="mt-1 font-medium">{settings.data.real_provider_configured ? "已配置" : "未启用，不产生费用"}</dd></div>
            <div><dt className="text-[var(--muted)]">视觉提供商</dt><dd className="mt-1 font-medium">{settings.data.vision_provider}</dd></div>
            <div><dt className="text-[var(--muted)]">视觉模型</dt><dd className="mt-1 font-medium">{settings.data.vision_model ?? "未配置（Mock 不需要）"}</dd></div>
            <div><dt className="text-[var(--muted)]">真实图片识别</dt><dd className="mt-1 font-medium">{settings.data.real_vision_provider_configured ? "已配置" : "未启用，不产生费用"}</dd></div>
          </dl>
        ) : null}
      </section>
      <section className="card mt-4">
        <h2 className="font-semibold">我的 AI 使用额度</h2>
        {usage.data ? (
          usage.data.access_enabled ? (
            <p className="mt-3 text-sm leading-7">{usage.data.month} 已使用 <strong>{usage.data.jobs_used}</strong> / {usage.data.monthly_job_limit} 次生成，还可使用 <strong>{usage.data.jobs_remaining}</strong> 次。额度用完后仍可继续手工编辑和记录。</p>
          ) : (
            <p className="mt-3 text-sm leading-7 text-[var(--muted)]">当前账户尚未开通 AI 生成额度；学生、课程、资料和所有手工功能不受影响。</p>
          )
        ) : <p className="mt-3 text-sm text-[var(--muted)]">正在读取额度…</p>}
      </section>
      <div className="mt-5 grid gap-6 lg:grid-cols-[260px_1fr]">
        <aside className="card h-fit">
          <h2 className="font-semibold">教案模板</h2>
          <div className="mt-3 space-y-2">
            {templates.data?.map((template) => (
              <button
                className={`w-full rounded-lg p-3 text-left text-sm ${selected?.id === template.id ? "bg-slate-900 text-white" : "bg-slate-50"}`}
                key={template.id}
                onClick={() => setSelectedId(template.id)}
              >
                <strong className="block">{template.name}</strong>
                <span className="opacity-70">
                  {template.grade_band ?? "通用"} · v{template.current_version_number}
                </span>
              </button>
            ))}
          </div>
        </aside>
        {selected ? (
          <form className="card space-y-4" key={`${selected.id}-${selected.current_version_number}`} onSubmit={save}>
            <label className="block"><span className="label">模板名称</span><input className="field" name="name" defaultValue={selected.name} required /></label>
            <label className="block"><span className="label">系统提示词</span><textarea className="field min-h-48 font-mono text-sm" name="system_prompt" defaultValue={selected.current_version.system_prompt} required /></label>
            <label className="block"><span className="label">用户提示词模板</span><textarea className="field min-h-72 font-mono text-sm" name="user_prompt_template" defaultValue={selected.current_version.user_prompt_template} required /></label>
            <label className="block"><span className="label">版本变更原因</span><input className="field" name="change_reason" placeholder="例如：调整初中教案的练习梯度" required /></label>
            <p className="text-xs text-[var(--muted)]">保存会创建新版本，不会覆盖历史模板。输出 JSON Schema 由系统统一维护，避免模板修改破坏教案契约。</p>
            <button className="button-primary">保存为新版本</button>
          </form>
        ) : (
          <EmptyState>正在初始化通用教案模板…</EmptyState>
        )}
      </div>
    </>
  );
}
