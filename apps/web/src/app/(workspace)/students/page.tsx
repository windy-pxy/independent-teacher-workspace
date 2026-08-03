"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useMemo, useState } from "react";

import { EmptyState, ErrorNotice, PageHeader } from "@/components/page-ui";
import { api, jsonBody } from "@/lib/api";
import type { Student, StudentSubject, Subject } from "@/lib/types";

const blankStudent = { display_name: "", grade: "", region: "", school: "", learning_characteristics: "", guardian_requirements: "", notes: "" };

export default function StudentsPage() {
  const client = useQueryClient();
  const students = useQuery({ queryKey: ["students"], queryFn: () => api<Student[]>("/students") });
  const subjects = useQuery({ queryKey: ["subjects"], queryFn: () => api<Subject[]>("/subjects") });
  const links = useQuery({ queryKey: ["student-subjects"], queryFn: () => api<StudentSubject[]>("/student-subjects") });
  const [selectedId, setSelectedId] = useState<string>();
  const [form, setForm] = useState(blankStudent);
  const [subjectId, setSubjectId] = useState("");
  const [textbook, setTextbook] = useState("");
  const [error, setError] = useState<unknown>();
  const selected = students.data?.find((row) => row.id === selectedId) ?? students.data?.[0];
  const selectedLinks = useMemo(() => links.data?.filter((row) => row.student_id === selected?.id) ?? [], [links.data, selected?.id]);

  async function refresh() {
    await Promise.all([client.invalidateQueries({ queryKey: ["students"] }), client.invalidateQueries({ queryKey: ["student-subjects"] })]);
  }
  async function create(event: FormEvent) {
    event.preventDefault(); setError(undefined);
    try {
      const payload = Object.fromEntries(Object.entries(form).map(([key, value]) => [key, value || null]));
      const row = await api<Student>("/students", { method: "POST", ...jsonBody(payload) });
      setForm(blankStudent); setSelectedId(row.id); await refresh();
    } catch (caught) { setError(caught); }
  }
  async function edit(row: Student) {
    const displayName = window.prompt("学生姓名或代号", row.display_name); if (!displayName) return;
    const grade = window.prompt("年级", row.grade ?? ""); if (grade === null) return;
    const foundation = window.prompt("学习特点", row.learning_characteristics ?? ""); if (foundation === null) return;
    try { await api(`/students/${row.id}`, { method: "PUT", ...jsonBody({ ...row, display_name: displayName, grade: grade || null, learning_characteristics: foundation || null, version: row.version }) }); await refresh(); } catch (caught) { setError(caught); }
  }
  async function archive(row: Student) {
    const reason = window.prompt(`确认归档“${row.display_name}”？请先确保没有计划中的课程，并输入原因`); if (!reason) return;
    try { await api(`/students/${row.id}/archive`, { method: "POST", ...jsonBody({ version: row.version, reason }) }); setSelectedId(undefined); await refresh(); } catch (caught) { setError(caught); }
  }
  async function attach(event: FormEvent) {
    event.preventDefault(); if (!selected || !subjectId) return;
    try { await api("/student-subjects", { method: "POST", ...jsonBody({ student_id: selected.id, subject_id: subjectId, textbook_version: textbook || null }) }); setSubjectId(""); setTextbook(""); await refresh(); } catch (caught) { setError(caught); }
  }
  async function editLink(row: StudentSubject) {
    const textbookVersion = window.prompt("教材版本", row.textbook_version ?? ""); if (textbookVersion === null) return;
    const currentFoundation = window.prompt("当前基础", row.current_foundation ?? ""); if (currentFoundation === null) return;
    const stageGoal = window.prompt("阶段目标", row.stage_goal ?? ""); if (stageGoal === null) return;
    try { await api(`/student-subjects/${row.id}`, { method: "PUT", ...jsonBody({ textbook_version: textbookVersion || null, current_foundation: currentFoundation || null, overall_goal: row.overall_goal, stage_goal: stageGoal || null, teaching_requirements: row.teaching_requirements, attention_notes: row.attention_notes, version: row.version }) }); await refresh(); } catch (caught) { setError(caught); }
  }

  return <>
    <PageHeader title="学生档案" description="通用情况保存在学生档案；教材、基础、目标与要求按学科独立保存。" />
    {error ? <ErrorNotice error={error} /> : null}
    <div className="mt-4 grid gap-6 xl:grid-cols-[260px_1fr_340px]">
      <section className="card h-fit"><h2 className="mb-3 font-semibold">学生</h2>{students.isPending ? <p>读取中…</p> : students.data?.length ? <div className="space-y-2">{students.data.map((row) => <button key={row.id} className={`w-full rounded-lg px-3 py-2 text-left text-sm ${selected?.id === row.id ? "bg-slate-900 text-white" : "bg-slate-50 hover:bg-slate-100"}`} onClick={() => setSelectedId(row.id)}><span className="font-medium">{row.display_name}</span><span className="ml-2 opacity-70">{row.grade}</span></button>)}</div> : <p className="text-sm text-[var(--muted)]">暂无学生</p>}</section>
      <section>{selected ? <div className="space-y-4"><article className="card"><div className="flex justify-between gap-4"><div><h2 className="text-xl font-semibold">{selected.display_name}</h2><p className="mt-2 text-sm text-[var(--muted)]">{[selected.grade, selected.region, selected.school].filter(Boolean).join(" · ") || "尚未填写基础信息"}</p></div><div className="flex gap-2"><button className="button-secondary" onClick={() => edit(selected)}>编辑</button><button className="button-danger" onClick={() => archive(selected)}>归档</button></div></div><dl className="mt-5 grid gap-4 text-sm md:grid-cols-2"><div><dt className="text-[var(--muted)]">学习特点</dt><dd className="mt-1">{selected.learning_characteristics || "—"}</dd></div><div><dt className="text-[var(--muted)]">家长要求</dt><dd className="mt-1">{selected.guardian_requirements || "—"}</dd></div></dl></article><article className="card"><h2 className="font-semibold">学科档案</h2>{selectedLinks.length ? <div className="mt-3 space-y-3">{selectedLinks.map((row) => <div className="rounded-xl border border-[var(--border)] p-4" key={row.id}><div className="flex justify-between"><strong>{row.subject_name}</strong><button className="button-secondary" onClick={() => editLink(row)}>编辑</button></div><p className="mt-2 text-sm text-[var(--muted)]">教材：{row.textbook_version || "未填写"}</p><p className="mt-1 text-sm">阶段目标：{row.stage_goal || "未填写"}</p></div>)}</div> : <p className="mt-3 text-sm text-[var(--muted)]">尚未关联学科。</p>}<form className="mt-5 grid gap-3 md:grid-cols-3" onSubmit={attach}><select className="field" value={subjectId} onChange={(e) => setSubjectId(e.target.value)} required><option value="">选择学科</option>{subjects.data?.filter((subject) => !selectedLinks.some((link) => link.subject_id === subject.id)).map((subject) => <option key={subject.id} value={subject.id}>{subject.name}</option>)}</select><input className="field" placeholder="教材版本（可选）" value={textbook} onChange={(e) => setTextbook(e.target.value)} /><button className="button-primary">关联学科</button></form></article></div> : <EmptyState>创建或选择一名学生。</EmptyState>}</section>
      <aside className="card h-fit"><h2 className="text-lg font-semibold">新增学生</h2><form className="mt-4 space-y-3" onSubmit={create}>{(["display_name","grade","region","school"] as const).map((key) => <label key={key}><span className="label">{{display_name:"姓名或代号",grade:"年级",region:"地区",school:"学校"}[key]}</span><input className="field" required={key === "display_name"} value={form[key]} onChange={(e) => setForm({...form,[key]:e.target.value})} /></label>)}<label><span className="label">学习特点</span><textarea className="field" value={form.learning_characteristics} onChange={(e) => setForm({...form,learning_characteristics:e.target.value})} /></label><button className="button-primary w-full">创建学生</button></form></aside>
    </div>
  </>;
}
