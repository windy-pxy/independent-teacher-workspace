"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { EmptyState, ErrorNotice, PageHeader } from "@/components/page-ui";
import { api } from "@/lib/api";
import type { Dashboard, Lesson } from "@/lib/types";

const formatter = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  month: "numeric",
  day: "numeric",
  weekday: "short",
  hour: "2-digit",
  minute: "2-digit",
});

function LessonList({ rows }: { rows: Lesson[] }) {
  if (!rows.length) return <p className="text-sm text-[var(--muted)]">暂无课程</p>;
  return (
    <ul className="divide-y divide-[var(--border)]">
      {rows.map((lesson) => (
        <li key={lesson.id} className="flex items-start justify-between gap-3 py-3 first:pt-0 last:pb-0">
          <div><p className="font-medium">{lesson.student_name} · {lesson.subject_name}</p><p className="mt-1 text-sm text-[var(--muted)]">{lesson.theme}</p></div>
          <time className="whitespace-nowrap text-sm">{formatter.format(new Date(lesson.scheduled_start))}</time>
        </li>
      ))}
    </ul>
  );
}

export default function DashboardPage() {
  const query = useQuery({ queryKey: ["dashboard"], queryFn: () => api<Dashboard>("/dashboard") });
  return (
    <>
      <PageHeader title="仪表盘" description="今天、未来七天和当前教学进度。收费、AI 与反馈数据将在对应阶段开放。" />
      {query.error ? <ErrorNotice error={query.error} /> : null}
      {query.isPending ? <EmptyState>正在读取仪表盘…</EmptyState> : null}
      {query.data ? (
        <div className="space-y-6">
          <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="card"><p className="text-sm text-[var(--muted)]">今日课程</p><p className="mt-2 text-3xl font-semibold">{query.data.today.length}</p></div>
            <div className="card"><p className="text-sm text-[var(--muted)]">未来七天</p><p className="mt-2 text-3xl font-semibold">{query.data.next_seven_days.length}</p></div>
            <div className="card"><p className="text-sm text-[var(--muted)]">本周课程</p><p className="mt-2 text-3xl font-semibold">{query.data.planned_this_week}</p></div>
            <div className="card"><p className="text-sm text-[var(--muted)]">本月已完成</p><p className="mt-2 text-3xl font-semibold">{query.data.completed_this_month}</p></div>
          </section>
          <section className="grid gap-6 xl:grid-cols-2">
            <div className="card"><div className="mb-4 flex justify-between"><h2 className="text-lg font-semibold">今天</h2><Link className="text-sm text-[var(--accent)]" href="/lessons">查看课表</Link></div><LessonList rows={query.data.today} /></div>
            <div className="card"><h2 className="mb-4 text-lg font-semibold">未来七天</h2><LessonList rows={query.data.next_seven_days} /></div>
          </section>
          <section className="card">
            <h2 className="mb-4 text-lg font-semibold">学生教学进度</h2>
            {query.data.progress.length ? <div className="grid gap-4 md:grid-cols-2">{query.data.progress.map((row) => <div key={row.student_subject_id}><div className="mb-2 flex justify-between text-sm"><span>{row.student_name} · {row.subject_name}</span><span>{row.completed_items}/{row.total_items}</span></div><div className="h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full bg-[var(--accent)]" style={{ width: `${row.percent}%` }} /></div></div>)}</div> : <p className="text-sm text-[var(--muted)]">创建学生学科和教学计划后，这里会显示结构化进度。</p>}
          </section>
        </div>
      ) : null}
    </>
  );
}
