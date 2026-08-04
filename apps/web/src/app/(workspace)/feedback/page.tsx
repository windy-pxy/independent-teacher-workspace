"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { EmptyState, ErrorNotice, PageHeader } from "@/components/page-ui";
import { ApiError, api, jsonBody } from "@/lib/api";
import type {
  AIJob,
  FeedbackVersion,
  Lesson,
  LessonFeedback,
  LessonFeedbackContent,
  Mastery,
  Plan,
} from "@/lib/types";

const reviewLabels = {
  DRAFT: "草稿",
  PENDING_REVIEW: "待审核",
  APPROVED: "已批准",
  REJECTED: "已驳回",
  SUPERSEDED: "已取代",
} as const;
const masteryLabels = {
  UNLEARNED: "未学习",
  WEAK: "薄弱",
  DEVELOPING: "一般",
  PROFICIENT: "熟练",
  MASTERED: "已掌握",
} as const;

function LinesEditor({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string[];
  onChange: (value: string[]) => void;
}) {
  return (
    <label className="block">
      <span className="label">{label}（每行一项）</span>
      <textarea
        className="field min-h-24"
        value={value.join("\n")}
        onChange={(event) =>
          onChange(event.target.value.split("\n").filter((line) => line.trim()))
        }
      />
    </label>
  );
}

export default function FeedbackPage() {
  const searchParams = useSearchParams();
  const client = useQueryClient();
  const lessons = useQuery({
    queryKey: ["lessons", "feedback"],
    queryFn: () => api<Lesson[]>("/lessons"),
  });
  const completedLessons = useMemo(
    () => lessons.data?.filter((lesson) => lesson.status === "COMPLETED") ?? [],
    [lessons.data],
  );
  const [lessonId, setLessonId] = useState(searchParams.get("lesson") ?? "");
  const selectedLesson = completedLessons.find((lesson) => lesson.id === lessonId);
  const feedback = useQuery({
    queryKey: ["lesson-feedback", lessonId],
    queryFn: () => api<LessonFeedback>(`/lessons/${lessonId}/feedback`),
    enabled: Boolean(lessonId),
    retry: (count, caught) =>
      caught instanceof ApiError && caught.status === 404 ? false : count < 2,
  });
  const plans = useQuery({
    queryKey: ["plans"],
    queryFn: () => api<Plan[]>("/teaching-plans"),
  });
  const versions = useQuery({
    queryKey: ["feedback-versions", feedback.data?.id],
    queryFn: () =>
      api<FeedbackVersion[]>(`/lesson-feedbacks/${feedback.data!.id}/versions`),
    enabled: Boolean(feedback.data),
  });
  const mastery = useQuery({
    queryKey: ["mastery", selectedLesson?.student_subject_id],
    queryFn: () =>
      api<Mastery[]>(`/student-subjects/${selectedLesson!.student_subject_id}/mastery`),
    enabled: Boolean(selectedLesson),
  });
  const [quick, setQuick] = useState({
    actual_completed_content: "",
    unfinished_content: "",
    student_performance: "",
    strong_knowledge_points: "",
    weak_knowledge_points: "",
    typical_mistakes: "",
    homework_completion: "",
    next_lesson_special_arrangement: "",
  });
  const [draftEdit, setDraftEdit] = useState<{
    version: number;
    content: LessonFeedbackContent;
  }>();
  const [jobId, setJobId] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const job = useQuery({
    queryKey: ["ai-job", jobId],
    queryFn: () => api<AIJob>(`/ai-jobs/${jobId}`),
    enabled: Boolean(jobId),
    refetchInterval: (query) =>
      ["SUCCEEDED", "FAILED", "CANCELED"].includes(query.state.data?.status ?? "")
        ? false
        : 1000,
  });

  useEffect(() => {
    if (job.data?.status === "SUCCEEDED") {
      void client.invalidateQueries({ queryKey: ["lesson-feedback", lessonId] });
      void client.invalidateQueries({ queryKey: ["feedback-versions"] });
    }
  }, [client, job.data, lessonId]);
  const draft =
    draftEdit && draftEdit.version === feedback.data?.current_version_number
      ? draftEdit.content
      : feedback.data?.current_version.content;
  const setDraft = (content: LessonFeedbackContent) => {
    if (feedback.data) {
      setDraftEdit({ version: feedback.data.current_version_number, content });
    }
  };
  const jobRunning = Boolean(
    jobId && !["SUCCEEDED", "FAILED", "CANCELED"].includes(job.data?.status ?? ""),
  );
  const visibleError =
    job.data?.status === "FAILED"
      ? new Error(job.data.error_message ?? "AI 整理失败")
      : error;

  const planItemLabels = useMemo(
    () =>
      new Map(
        (plans.data ?? [])
          .filter((plan) => plan.student_subject_id === selectedLesson?.student_subject_id)
          .flatMap((plan) => plan.items ?? [])
          .map((item) => [item.id, item.title]),
      ),
    [plans.data, selectedLesson?.student_subject_id],
  );

  async function refresh() {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["lesson-feedback", lessonId] }),
      client.invalidateQueries({ queryKey: ["feedback-versions"] }),
      client.invalidateQueries({ queryKey: ["mastery"] }),
      client.invalidateQueries({ queryKey: ["plans"] }),
      client.invalidateQueries({ queryKey: ["dashboard"] }),
    ]);
  }
  async function saveQuick(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await api(`/lessons/${lessonId}/feedback/drafts`, {
        method: "POST",
        ...jsonBody(quick),
      });
      await refresh();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }
  async function organize() {
    if (!feedback.data) return;
    setBusy(true);
    setError(undefined);
    try {
      const queued = await api<AIJob>(`/lesson-feedbacks/${feedback.data.id}/organize`, {
        method: "POST",
        ...jsonBody({ instructions: null, version: feedback.data.version }),
      });
      setJobId(queued.id);
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }
  async function saveStructured() {
    if (!feedback.data || !draft) return;
    const summary = window.prompt("请填写本次修改说明", "教师复核并修订结构化反馈");
    if (!summary) return;
    setBusy(true);
    try {
      await api(`/lesson-feedbacks/${feedback.data.id}`, {
        method: "PUT",
        ...jsonBody({ content: draft, change_summary: summary, version: feedback.data.version }),
      });
      await refresh();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }
  async function transition(action: "submit" | "approve" | "reject") {
    if (!feedback.data) return;
    const reason = window.prompt(
      action === "approve" ? "批准后将正式同步进度与掌握度，请填写确认说明" : "请填写操作说明",
    );
    if (!reason) return;
    setBusy(true);
    try {
      await api(`/lesson-feedbacks/${feedback.data.id}/${action}`, {
        method: "POST",
        ...jsonBody({ reason, version: feedback.data.version }),
      });
      await refresh();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="课后反馈"
        description="少量关键词先保存为草稿，AI 整理后由教师审核；批准前不会改动正式教学进度或知识点掌握度。"
      />
      {visibleError ? <ErrorNotice error={visibleError} /> : null}
      <section className="card mt-5">
        <label className="block">
          <span className="label">选择已完成课程</span>
          <select
            className="field"
            value={lessonId}
            onChange={(event) => {
              setLessonId(event.target.value);
              setJobId(undefined);
              setError(undefined);
            }}
          >
            <option value="">请选择课程</option>
            {completedLessons.map((lesson) => (
              <option value={lesson.id} key={lesson.id}>
                {lesson.student_name} · {lesson.subject_name} · {lesson.theme}
              </option>
            ))}
          </select>
        </label>
      </section>
      {!lessonId ? (
        <EmptyState>先选择一节已完成课程。若列表为空，请到<Link className="underline" href="/lessons">课程与课表</Link>完成课程。</EmptyState>
      ) : feedback.error instanceof ApiError && feedback.error.status === 404 ? (
        <section className="card mt-5">
          <h2 className="font-semibold">快速填写关键词</h2>
          <form className="mt-4 grid gap-4 md:grid-cols-2" onSubmit={saveQuick}>
            {Object.entries({
              actual_completed_content: "实际完成内容",
              unfinished_content: "未完成内容",
              student_performance: "学生表现",
              strong_knowledge_points: "掌握较好的知识点",
              weak_knowledge_points: "薄弱知识点",
              typical_mistakes: "典型错误",
              homework_completion: "作业完成情况",
              next_lesson_special_arrangement: "下节课特殊安排",
            }).map(([field, label]) => (
              <label key={field} className="block">
                <span className="label">{label}</span>
                <textarea
                  className="field min-h-20"
                  placeholder="可只填关键词，用逗号或换行分隔"
                  value={quick[field as keyof typeof quick]}
                  onChange={(event) => setQuick({ ...quick, [field]: event.target.value })}
                />
              </label>
            ))}
            <button className="button-primary md:col-span-2" disabled={busy}>保存关键词草稿</button>
          </form>
        </section>
      ) : feedback.isPending ? (
        <EmptyState>正在读取反馈…</EmptyState>
      ) : feedback.error ? (
        <ErrorNotice error={feedback.error} />
      ) : feedback.data && draft ? (
        <div className="mt-5 grid gap-5 xl:grid-cols-[1fr_300px]">
          <div className="space-y-5">
            <section className="card flex flex-wrap items-center justify-between gap-3">
              <div>
                <span className="badge">{reviewLabels[feedback.data.status]}</span>
                <p className="mt-2 text-sm text-[var(--muted)]">当前版本 v{feedback.data.current_version_number} · {feedback.data.current_version.source}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                {feedback.data.status === "DRAFT" || feedback.data.status === "REJECTED" ? <button className="button-secondary" disabled={busy || jobRunning} onClick={organize}>{jobRunning ? "AI 整理中…" : "用 AI 整理"}</button> : null}
                {feedback.data.status === "DRAFT" || feedback.data.status === "REJECTED" ? <button className="button-secondary" disabled={busy} onClick={saveStructured}>保存人工修订</button> : null}
                {feedback.data.status === "DRAFT" || feedback.data.status === "REJECTED" ? <button className="button-primary" disabled={busy} onClick={() => transition("submit")}>提交审核</button> : null}
                {feedback.data.status === "PENDING_REVIEW" ? <><button className="button-danger" disabled={busy} onClick={() => transition("reject")}>驳回</button><button className="button-primary" disabled={busy} onClick={() => transition("approve")}>批准并同步</button></> : null}
              </div>
            </section>
            <section className="card grid gap-4 md:grid-cols-2">
              <LinesEditor label="实际完成内容" value={draft.actual_completed_content} onChange={(value) => setDraft({ ...draft, actual_completed_content: value })} />
              <LinesEditor label="未完成内容" value={draft.unfinished_content} onChange={(value) => setDraft({ ...draft, unfinished_content: value })} />
              <LinesEditor label="掌握较好的知识点" value={draft.strong_knowledge_points} onChange={(value) => setDraft({ ...draft, strong_knowledge_points: value })} />
              <LinesEditor label="薄弱知识点" value={draft.weak_knowledge_points} onChange={(value) => setDraft({ ...draft, weak_knowledge_points: value })} />
              <LinesEditor label="典型错误" value={draft.typical_mistakes} onChange={(value) => setDraft({ ...draft, typical_mistakes: value })} />
              {(["student_performance", "homework_completion", "next_lesson_special_arrangement", "structured_summary", "next_lesson_suggestion"] as const).map((field) => <label className="block" key={field}><span className="label">{{ student_performance: "学生表现", homework_completion: "作业完成情况", next_lesson_special_arrangement: "下节课特殊安排", structured_summary: "结构化总结", next_lesson_suggestion: "下次课建议" }[field]}</span><textarea className="field min-h-24" value={draft[field]} onChange={(event) => setDraft({ ...draft, [field]: event.target.value })} /></label>)}
            </section>
            <section className="card">
              <h2 className="font-semibold">计划进度变更（批准后生效）</h2>
              <div className="mt-4 space-y-3">{draft.plan_progress_updates.length ? draft.plan_progress_updates.map((update, index) => <div className="grid gap-3 rounded-xl border border-[var(--border)] p-4 md:grid-cols-3" key={update.plan_item_id}><div className="text-sm font-medium">{planItemLabels.get(update.plan_item_id) ?? update.plan_item_id}</div><select className="field" value={update.status} onChange={(event) => { const next=[...draft.plan_progress_updates]; next[index]={...update,status:event.target.value as typeof update.status}; setDraft({...draft,plan_progress_updates:next}); }}><option value="IN_PROGRESS">进行中</option><option value="COMPLETED">已完成</option><option value="REVIEW_NEEDED">需要复习</option></select><input className="field" type="number" min="0" value={update.actual_minutes_delta} onChange={(event) => { const next=[...draft.plan_progress_updates]; next[index]={...update,actual_minutes_delta:Number(event.target.value)}; setDraft({...draft,plan_progress_updates:next}); }} /><textarea className="field md:col-span-3" value={update.progress_note} onChange={(event) => { const next=[...draft.plan_progress_updates]; next[index]={...update,progress_note:event.target.value}; setDraft({...draft,plan_progress_updates:next}); }} /></div>) : <p className="text-sm text-[var(--muted)]">当前没有建议的计划变更。</p>}</div>
            </section>
            <section className="card">
              <div className="flex items-center justify-between"><h2 className="font-semibold">掌握度变更（批准后生效）</h2>{feedback.data.status !== "APPROVED" ? <button className="button-secondary" onClick={() => setDraft({...draft,mastery_updates:[...draft.mastery_updates,{knowledge_point_id:null,knowledge_point_name:"新知识点",level:"DEVELOPING",evidence_note:"教师人工补充证据"}]})}>新增知识点</button> : null}</div>
              <div className="mt-4 space-y-3">{draft.mastery_updates.map((update,index) => <div className="grid gap-3 rounded-xl border border-[var(--border)] p-4 md:grid-cols-3" key={`${update.knowledge_point_id ?? "new"}-${index}`}><input className="field" value={update.knowledge_point_name} onChange={(event) => { const next=[...draft.mastery_updates]; next[index]={...update,knowledge_point_name:event.target.value}; setDraft({...draft,mastery_updates:next}); }} /><select className="field" value={update.level} onChange={(event) => { const next=[...draft.mastery_updates]; next[index]={...update,level:event.target.value as typeof update.level}; setDraft({...draft,mastery_updates:next}); }}>{Object.entries(masteryLabels).map(([value,label]) => <option value={value} key={value}>{label}</option>)}</select><button className="button-danger" type="button" onClick={() => setDraft({...draft,mastery_updates:draft.mastery_updates.filter((_,rowIndex) => rowIndex !== index)})}>移除</button><textarea className="field md:col-span-3" value={update.evidence_note} onChange={(event) => { const next=[...draft.mastery_updates]; next[index]={...update,evidence_note:event.target.value}; setDraft({...draft,mastery_updates:next}); }} /></div>)}</div>
            </section>
          </div>
          <aside className="space-y-5">
            <section className="card"><h2 className="font-semibold">版本历史</h2><div className="mt-3 space-y-2">{versions.data?.map((version) => <div className="rounded-lg border border-[var(--border)] p-3 text-sm" key={version.id}><strong>v{version.version_number}</strong> · {reviewLabels[version.status]}<p className="mt-1 text-[var(--muted)]">{version.change_summary}</p></div>)}</div></section>
            <section className="card"><h2 className="font-semibold">正式掌握度</h2><p className="mt-1 text-xs text-[var(--muted)]">这里只显示已经通过反馈批准写入的记录。</p><div className="mt-3 space-y-2">{mastery.data?.length ? mastery.data.map((row) => <div className="flex items-center justify-between gap-2 text-sm" key={row.id}><span>{row.knowledge_point_name}</span><span className="badge">{masteryLabels[row.level]}</span></div>) : <p className="text-sm text-[var(--muted)]">暂无正式记录</p>}</div></section>
          </aside>
        </div>
      ) : null}
    </>
  );
}
