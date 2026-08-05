"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { EmptyState, ErrorNotice, PageHeader } from "@/components/page-ui";
import { api, jsonBody } from "@/lib/api";
import type { AIJob, StudentSubject } from "@/lib/types";

type WrongQuestion = {
  id: string;
  student_subject_id: string;
  status: string;
  current_version: { content: { question_text: string; knowledge_points: { knowledge_point_id: string | null; name: string }[] } };
};
type Question = {
  question_key: string;
  stem_markdown: string;
  answer_markdown: string;
  analysis_markdown: string;
  difficulty: string;
  knowledge_points: { knowledge_point_id: string | null; name: string }[];
};
type QuestionSet = {
  id: string;
  student_subject_id: string;
  student_name: string;
  subject_name: string;
  title: string;
  status: "DRAFT" | "PENDING_REVIEW" | "APPROVED" | "REJECTED" | "SUPERSEDED";
  version: number;
  current_version: null | { version_number: number; content: { title: string; teacher_notes: string; questions: Question[] } };
};
type Generated = { question_set: QuestionSet; job: AIJob };

export default function PracticePage() {
  const client = useQueryClient();
  const subjects = useQuery({ queryKey: ["student-subjects"], queryFn: () => api<StudentSubject[]>("/student-subjects") });
  const wrongQuestions = useQuery({ queryKey: ["wrong-questions"], queryFn: () => api<WrongQuestion[]>("/wrong-questions") });
  const sets = useQuery({ queryKey: ["question-sets"], queryFn: () => api<QuestionSet[]>("/question-sets") });
  const [subjectId, setSubjectId] = useState("");
  const [title, setTitle] = useState("薄弱知识点针对性练习");
  const [quantity, setQuantity] = useState(5);
  const [difficulty, setDifficulty] = useState("MEDIUM");
  const [requirements, setRequirements] = useState("");
  const [selectedWrong, setSelectedWrong] = useState<string[]>([]);
  const [jobId, setJobId] = useState<string>();
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const job = useQuery({
    queryKey: ["ai-job", jobId],
    queryFn: () => api<AIJob>(`/ai-jobs/${jobId}`),
    enabled: Boolean(jobId),
    refetchInterval: (query) => ["SUCCEEDED", "FAILED", "CANCELED"].includes(query.state.data?.status ?? "") ? false : 1000,
  });
  useEffect(() => {
    if (job.data?.status === "SUCCEEDED") void client.invalidateQueries({ queryKey: ["question-sets"] });
  }, [client, job.data?.status]);
  const availableWrong = useMemo(
    () => (wrongQuestions.data ?? []).filter((item) => item.student_subject_id === subjectId && item.status === "APPROVED"),
    [subjectId, wrongQuestions.data],
  );

  async function refresh() {
    await client.invalidateQueries({ queryKey: ["question-sets"] });
  }
  async function generate(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      const selected = availableWrong.filter((item) => selectedWrong.includes(item.id));
      const knowledgeIds = Array.from(new Set(selected.flatMap((item) => item.current_version.content.knowledge_points.map((point) => point.knowledge_point_id).filter((id): id is string => Boolean(id)))));
      const result = await api<Generated>("/question-sets/generate", {
        method: "POST",
        ...jsonBody({
          student_subject_id: subjectId,
          title,
          quantity,
          target_difficulty: difficulty,
          extra_requirements: requirements || null,
          knowledge_point_ids: knowledgeIds,
          wrong_question_ids: selectedWrong,
        }),
      });
      setJobId(result.job.id);
      await refresh();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }
  async function transition(item: QuestionSet, action: "submit" | "approve" | "reject") {
    const reason = window.prompt(action === "approve" ? "请确认每道题均已核对答案和解析，并填写批准说明" : "操作说明");
    if (!reason) return;
    try {
      await api(`/question-sets/${item.id}/${action}`, { method: "POST", ...jsonBody({ reason, version: item.version }) });
      await refresh();
    } catch (caught) {
      setError(caught);
    }
  }
  async function edit(item: QuestionSet) {
    if (!item.current_version) return;
    const nextTitle = window.prompt("练习标题", item.current_version.content.title);
    if (!nextTitle) return;
    const notes = window.prompt("教师备注", item.current_version.content.teacher_notes);
    if (notes === null) return;
    const reason = window.prompt("版本修改说明", "教师核对并调整练习信息");
    if (!reason) return;
    try {
      await api(`/question-sets/${item.id}`, {
        method: "PUT",
        ...jsonBody({
          version: item.version,
          change_summary: reason,
          content: { ...item.current_version.content, title: nextTitle, teacher_notes: notes },
        }),
      });
      await refresh();
    } catch (caught) {
      setError(caught);
    }
  }

  const visibleError = job.data?.status === "FAILED" ? new Error(job.data.error_message ?? "练习生成失败") : error;
  return <>
    <PageHeader title="针对性练习" description="综合正式错题、错误原因、知识点和学生水平生成；所有题目都含答案与解析，批准前仅为草稿。" />
    {visibleError ? <ErrorNotice error={visibleError} /> : null}
    <form className="card space-y-4" onSubmit={generate}>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <select className="field" required value={subjectId} onChange={(event) => { setSubjectId(event.target.value); setSelectedWrong([]); }}><option value="">选择学生与学科</option>{subjects.data?.map((item) => <option key={item.id} value={item.id}>{item.student_name} · {item.subject_name}</option>)}</select>
        <input className="field" required value={title} onChange={(event) => setTitle(event.target.value)} />
        <select className="field" value={difficulty} onChange={(event) => setDifficulty(event.target.value)}><option value="BASIC">基础</option><option value="MEDIUM">中等</option><option value="ADVANCED">进阶</option></select>
        <input className="field" type="number" min={1} max={30} value={quantity} onChange={(event) => setQuantity(Number(event.target.value))} />
      </div>
      <textarea className="field" placeholder="额外要求，例如：侧重计算、避免超纲" value={requirements} onChange={(event) => setRequirements(event.target.value)} />
      <fieldset><legend className="label">参考正式错题（可多选）</legend><div className="mt-2 grid gap-2 md:grid-cols-2">{availableWrong.map((item) => <label className="rounded-lg border border-[var(--border)] p-3 text-sm" key={item.id}><input className="mr-2" type="checkbox" checked={selectedWrong.includes(item.id)} onChange={(event) => setSelectedWrong(event.target.checked ? [...selectedWrong, item.id] : selectedWrong.filter((id) => id !== item.id))} />{item.current_version.content.question_text}</label>)}</div>{subjectId && !availableWrong.length ? <p className="mt-2 text-sm text-[var(--muted)]">该学生学科还没有已批准错题，也可根据学生基础直接生成。</p> : null}</fieldset>
      <button className="button-primary" disabled={busy || !subjectId}>生成练习草稿</button>
      {jobId ? <span className="ml-3 text-sm">任务状态：{job.data?.status ?? "QUEUED"}</span> : null}
    </form>
    <section className="mt-6 space-y-5">
      <h2 className="text-xl font-semibold">练习版本</h2>
      {sets.data?.length ? sets.data.map((item) => <article className="card" key={item.id}>
        <div className="flex flex-wrap justify-between gap-3"><div><p className="text-sm text-[var(--muted)]">{item.student_name} · {item.subject_name} · {item.status}</p><h3 className="mt-1 text-lg font-semibold">{item.title}</h3></div><div className="flex gap-2">{item.status !== "APPROVED" && item.current_version ? <button className="button-secondary" onClick={() => edit(item)}>编辑信息并保存新版本</button> : null}{item.status === "DRAFT" || item.status === "REJECTED" ? <button className="button-secondary" onClick={() => transition(item, "submit")}>提交审核</button> : null}{item.status === "PENDING_REVIEW" ? <><button className="button-primary" onClick={() => transition(item, "approve")}>批准发布</button><button className="button-danger" onClick={() => transition(item, "reject")}>驳回</button></> : null}</div></div>
        {item.current_version ? <><p className="mt-3 text-sm text-[var(--muted)]">版本 {item.current_version.version_number} · {item.current_version.content.teacher_notes || "无教师备注"}</p><div className="mt-4 space-y-3">{item.current_version.content.questions.map((question, index) => <details className="rounded-xl border border-[var(--border)] p-4" key={question.question_key}><summary className="cursor-pointer font-medium">{index + 1}. {question.stem_markdown}</summary><div className="mt-3 border-t pt-3 text-sm"><p><strong>答案：</strong>{question.answer_markdown}</p><p className="mt-2"><strong>解析：</strong>{question.analysis_markdown}</p></div></details>)}</div></> : <p className="mt-4 text-sm text-[var(--muted)]">正在等待后台生成草稿。</p>}
      </article>) : <EmptyState>还没有生成练习。</EmptyState>}
    </section>
  </>;
}
