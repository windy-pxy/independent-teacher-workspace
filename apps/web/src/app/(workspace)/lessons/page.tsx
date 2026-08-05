"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { FormEvent, useState } from "react";

import { EmptyState, ErrorNotice, PageHeader } from "@/components/page-ui";
import { api, jsonBody } from "@/lib/api";
import type { Lesson, LessonType, StudentSubject } from "@/lib/types";

const typeLabels: Record<LessonType, string> = { NEW_LESSON: "新课", REVIEW: "复习", EXERCISE: "习题课", EXAM: "考试", PAPER_REVIEW: "试卷讲评" };
const statusLabels = { PLANNED: "计划中", COMPLETED: "已完成", CANCELED: "已取消", RESCHEDULED: "已调课" } as const;
const lessonFormatter = new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", month: "numeric", day: "numeric", weekday: "short", hour: "2-digit", minute: "2-digit" });
const dayKey = (value: string | Date) => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai" }).format(new Date(value));
const yuanToCents = (value: string) => Math.round(Number(value || "0") * 100);

function MonthCalendar({ month, lessons }: { month: Date; lessons: Lesson[] }) {
  const first = new Date(month.getFullYear(), month.getMonth(), 1);
  const last = new Date(month.getFullYear(), month.getMonth() + 1, 0);
  const cells: (Date | null)[] = Array(first.getDay()).fill(null);
  for (let day = 1; day <= last.getDate(); day += 1) cells.push(new Date(month.getFullYear(), month.getMonth(), day));
  while (cells.length % 7) cells.push(null);
  return <div className="card overflow-x-auto"><div className="grid min-w-[720px] grid-cols-7 text-center text-xs font-medium text-[var(--muted)]">{"日一二三四五六".split("").map((day) => <div className="pb-3" key={day}>周{day}</div>)}</div><div className="grid min-w-[720px] grid-cols-7 border-l border-t border-[var(--border)]">{cells.map((date,index) => { const rows = date ? lessons.filter((lesson) => dayKey(lesson.scheduled_start) === dayKey(date)) : []; return <div key={`${date?.toISOString() ?? "blank"}-${index}`} className="min-h-28 border-b border-r border-[var(--border)] p-2"><span className="text-xs text-[var(--muted)]">{date?.getDate()}</span>{rows.map((lesson) => <div title={lesson.theme} className={`mt-1 rounded-md px-2 py-1 text-xs ${lesson.status === "CANCELED" || lesson.status === "RESCHEDULED" ? "bg-slate-100 text-slate-400 line-through" : "bg-emerald-50 text-emerald-900"}`} key={lesson.id}><strong>{new Date(lesson.scheduled_start).toLocaleTimeString("zh-CN",{hour:"2-digit",minute:"2-digit"})}</strong> {lesson.student_name}</div>)}</div>; })}</div></div>;
}

export default function LessonsPage() {
  const client = useQueryClient();
  const [month, setMonth] = useState(() => new Date());
  const [view, setView] = useState<"calendar" | "list">("calendar");
  const monthStart = new Date(month.getFullYear(), month.getMonth(), 1);
  const monthEnd = new Date(month.getFullYear(), month.getMonth() + 1, 1);
  const lessons = useQuery({ queryKey: ["lessons", month.getFullYear(), month.getMonth()], queryFn: () => api<Lesson[]>(`/lessons?start=${encodeURIComponent(monthStart.toISOString())}&end=${encodeURIComponent(monthEnd.toISOString())}`) });
  const links = useQuery({ queryKey: ["student-subjects"], queryFn: () => api<StudentSubject[]>("/student-subjects") });
  const [form, setForm] = useState({ student_subject_id: "", scheduled_start: "", planned_minutes: "120", unit_price_yuan: "0", lesson_type: "NEW_LESSON", theme: "", special_requirements: "", makeup_for_lesson_id: "" });
  const [error, setError] = useState<unknown>();
  const [completing, setCompleting] = useState<Lesson>();
  const [actualMinutes, setActualMinutes] = useState("120");

  async function refresh() { await Promise.all([client.invalidateQueries({ queryKey: ["lessons"] }), client.invalidateQueries({ queryKey: ["plans"] }), client.invalidateQueries({ queryKey: ["dashboard"] })]); }
  async function create(event: FormEvent) { event.preventDefault(); try { await api("/lessons", { method: "POST", ...jsonBody({ ...form, scheduled_start: new Date(form.scheduled_start).toISOString(), planned_minutes: Number(form.planned_minutes), unit_price_cents: yuanToCents(form.unit_price_yuan), lesson_type: form.lesson_type, special_requirements: form.special_requirements || null, plan_item_ids: [], makeup_for_lesson_id: form.makeup_for_lesson_id || null }) }); setForm({ student_subject_id: "", scheduled_start: "", planned_minutes: "120", unit_price_yuan: "0", lesson_type: "NEW_LESSON", theme: "", special_requirements: "", makeup_for_lesson_id: "" }); await refresh(); } catch (caught) { setError(caught); } }
  async function edit(row: Lesson) { const theme = window.prompt("课程主题", row.theme); if (!theme) return; const time = window.prompt("新时间（例如 2026-08-10T18:30）", new Date(row.scheduled_start).toISOString().slice(0,16)); if (!time) return; try { await api(`/lessons/${row.id}`, { method: "PUT", ...jsonBody({ scheduled_start: new Date(time).toISOString(), planned_minutes: row.planned_minutes, unit_price_cents: row.unit_price_cents, lesson_type: row.lesson_type, theme, special_requirements: row.special_requirements, plan_item_ids: row.plan_item_ids, version: row.version }) }); await refresh(); } catch (caught) { setError(caught); } }
  async function cancel(row: Lesson) { const reason = window.prompt("请输入取消原因"); if (!reason) return; try { await api(`/lessons/${row.id}/cancel`, { method: "POST", ...jsonBody({ reason, version: row.version }) }); await refresh(); } catch (caught) { setError(caught); } }
  async function reschedule(row: Lesson) { const time = window.prompt("调课后的时间（例如 2026-08-10T18:30）"); if (!time) return; const reason = window.prompt("调课原因"); if (!reason) return; try { await api(`/lessons/${row.id}/reschedule`, { method: "POST", ...jsonBody({ scheduled_start: new Date(time).toISOString(), planned_minutes: row.planned_minutes, reason, version: row.version }) }); await refresh(); } catch (caught) { setError(caught); } }
  function openComplete(row: Lesson) { setCompleting(row); setActualMinutes(String(row.planned_minutes)); }
  async function complete(event: FormEvent) { event.preventDefault(); if (!completing) return; try { await api(`/lessons/${completing.id}/complete`, { method: "POST", ...jsonBody({ actual_minutes: Number(actualMinutes), progress_updates: [], adjustment_reason: "课程已完成，计划进度等待课后反馈审核" }) }); setCompleting(undefined); await refresh(); } catch (caught) { setError(caught); } }

  return <>
    <PageHeader title="课程与课表" description="单节创建、列表/月历、完成确认、取消、调课与补课；重复课程暂不在 Phase 1 支持。" />
    {error ? <ErrorNotice error={error} /> : null}
    <section className="card mt-4">
      <h2 className="font-semibold">创建课程</h2>
      <form className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4" onSubmit={create}>
        <select className="field" value={form.student_subject_id} onChange={(e) => setForm({...form,student_subject_id:e.target.value})} required><option value="">学生 · 学科</option>{links.data?.map((row) => <option key={row.id} value={row.id}>{row.student_name} · {row.subject_name}</option>)}</select>
        <input className="field" type="datetime-local" value={form.scheduled_start} onChange={(e) => setForm({...form,scheduled_start:e.target.value})} required />
        <input className="field" aria-label="计划分钟" type="number" min="15" max="720" value={form.planned_minutes} onChange={(e) => setForm({...form,planned_minutes:e.target.value})} required />
        <input className="field" aria-label="每小时单价" type="number" min="0" step="0.01" placeholder="每小时单价（元）" value={form.unit_price_yuan} onChange={(e) => setForm({...form,unit_price_yuan:e.target.value})} required />
        <select className="field" value={form.lesson_type} onChange={(e) => setForm({...form,lesson_type:e.target.value})}>{Object.entries(typeLabels).map(([value,label]) => <option value={value} key={value}>{label}</option>)}</select>
        <input className="field xl:col-span-2" placeholder="本节主题" value={form.theme} onChange={(e) => setForm({...form,theme:e.target.value})} required />
        <select className="field" value={form.makeup_for_lesson_id} onChange={(e) => setForm({...form,makeup_for_lesson_id:e.target.value})}><option value="">普通课程</option>{lessons.data?.filter((row) => row.status === "CANCELED").map((row) => <option key={row.id} value={row.id}>补课：{row.student_name} · {row.theme}</option>)}</select>
        <button className="button-primary">创建课程</button>
      </form>
    </section>
    <div className="my-5 flex flex-wrap items-center justify-between gap-3"><div className="flex items-center gap-2"><button className="button-secondary" onClick={() => setMonth(new Date(month.getFullYear(),month.getMonth()-1,1))}>上月</button><strong>{month.getFullYear()} 年 {month.getMonth()+1} 月</strong><button className="button-secondary" onClick={() => setMonth(new Date(month.getFullYear(),month.getMonth()+1,1))}>下月</button></div><div className="flex gap-2"><button className={view === "calendar" ? "button-primary" : "button-secondary"} onClick={() => setView("calendar")}>月历</button><button className={view === "list" ? "button-primary" : "button-secondary"} onClick={() => setView("list")}>列表</button></div></div>
    {lessons.isPending ? <EmptyState>正在读取课表…</EmptyState> : lessons.error ? <ErrorNotice error={lessons.error} /> : view === "calendar" ? <MonthCalendar month={month} lessons={lessons.data ?? []} /> : lessons.data?.length ? <div className="space-y-3">{lessons.data.map((row) => <article className="card flex flex-wrap items-start justify-between gap-4" key={row.id}><div><div className="flex gap-2"><span className="badge">{statusLabels[row.status]}</span><span className="badge">{typeLabels[row.lesson_type]}</span></div><h2 className="mt-2 font-semibold">{row.student_name} · {row.subject_name}</h2><p className="mt-1 text-sm">{row.theme}</p><time className="mt-1 block text-sm text-[var(--muted)]">{lessonFormatter.format(new Date(row.scheduled_start))} · {row.planned_minutes} 分钟</time></div><div className="flex flex-wrap gap-2"><Link className="button-secondary" href={`/lesson-plans?lesson=${row.id}`}>教案</Link>{row.status === "COMPLETED" ? <Link className="button-primary" href={`/feedback?lesson=${row.id}`}>填写反馈</Link> : null}{row.status === "PLANNED" ? <><button className="button-secondary" onClick={() => edit(row)}>编辑</button><button className="button-primary" onClick={() => openComplete(row)}>完成课程</button><button className="button-secondary" onClick={() => reschedule(row)}>调课</button><button className="button-danger" onClick={() => cancel(row)}>取消</button></> : null}</div></article>)}</div> : <EmptyState>本月暂无课程。</EmptyState>}
    {completing ? <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/40 p-5" role="dialog" aria-modal="true" aria-labelledby="complete-title"><form className="card w-full max-w-2xl p-7" onSubmit={complete}><h2 id="complete-title" className="text-xl font-semibold">完成课程</h2><p className="mt-2 text-sm text-[var(--muted)]">{completing.student_name} · {completing.subject_name} · {completing.theme}</p><label className="mt-5 block"><span className="label">实际分钟</span><input className="field" type="number" min="1" max="720" value={actualMinutes} onChange={(e) => setActualMinutes(e.target.value)} required /></label><p className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">完成课程只记录实际时长。教学进度和知识点掌握度将在课后反馈经你批准后统一同步。</p><div className="mt-6 flex justify-end gap-3"><button type="button" className="button-secondary" onClick={() => setCompleting(undefined)}>返回</button><button className="button-primary">确认完成</button></div></form></div> : null}
  </>;
}
