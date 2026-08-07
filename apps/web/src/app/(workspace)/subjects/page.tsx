"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";

import { useActionDialog } from "@/components/action-dialog";
import { EmptyState, ErrorNotice, PageHeader } from "@/components/page-ui";
import { api, jsonBody } from "@/lib/api";
import type { Subject } from "@/lib/types";

export default function SubjectsPage() {
  const queryClient = useQueryClient();
  const openDialog = useActionDialog();
  const query = useQuery({ queryKey: ["subjects"], queryFn: () => api<Subject[]>("/subjects") });
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<unknown>();

  async function create(event: FormEvent) {
    event.preventDefault(); setError(undefined);
    try {
      await api<Subject>("/subjects", { method: "POST", ...jsonBody({ name, description: description || null }) });
      setName(""); setDescription(""); await queryClient.invalidateQueries({ queryKey: ["subjects"] });
    } catch (caught) { setError(caught); }
  }

  async function edit(row: Subject) {
    const values = await openDialog({
      title: "编辑学科",
      fields: [
        { name: "name", label: "学科名称", value: row.name, required: true },
        { name: "description", label: "学科说明", value: row.description, type: "textarea" },
      ],
    });
    if (!values) return;
    try {
      await api(`/subjects/${row.id}`, { method: "PUT", ...jsonBody({ name: values.name, description: values.description || null, version: row.version }) });
      await queryClient.invalidateQueries({ queryKey: ["subjects"] });
    } catch (caught) { setError(caught); }
  }

  async function archive(row: Subject) {
    const values = await openDialog({
      title: `归档“${row.name}”`,
      description: "归档前请确认没有仍在使用该学科的教学安排。",
      tone: "danger",
      submitLabel: "确认归档",
      fields: [{ name: "reason", label: "归档原因", type: "textarea", required: true }],
    });
    if (!values) return;
    try {
      await api(`/subjects/${row.id}/archive`, { method: "POST", ...jsonBody({ version: row.version, reason: values.reason }) });
      await queryClient.invalidateQueries({ queryKey: ["subjects"] });
    } catch (caught) { setError(caught); }
  }

  return <>
    <PageHeader title="学科" description="维护可复用的学科目录；每名学生的教材、目标和进度保存在独立关联中。" />
    <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
      <section>{query.error ? <ErrorNotice error={query.error} /> : null}{query.isPending ? <EmptyState>正在读取学科…</EmptyState> : query.data?.length ? <div className="space-y-3">{query.data.map((row) => <article className="card flex items-start justify-between gap-4" key={row.id}><div><h2 className="font-semibold">{row.name}</h2><p className="mt-1 text-sm text-[var(--muted)]">{row.description || "暂无说明"}</p></div><div className="flex gap-2"><button className="button-secondary" onClick={() => edit(row)}>编辑</button><button className="button-danger" onClick={() => archive(row)}>归档</button></div></article>)}</div> : <EmptyState>还没有学科，请从右侧创建。</EmptyState>}</section>
      <aside className="card h-fit"><h2 className="text-lg font-semibold">新增学科</h2><form className="mt-4 space-y-4" onSubmit={create}><label><span className="label">名称</span><input className="field" value={name} onChange={(e) => setName(e.target.value)} required /></label><label><span className="label">说明</span><textarea className="field min-h-24" value={description} onChange={(e) => setDescription(e.target.value)} /></label>{error ? <ErrorNotice error={error} /> : null}<button className="button-primary w-full">创建学科</button></form></aside>
    </div>
  </>;
}
