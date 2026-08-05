"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useState } from "react";

import { EmptyState, ErrorNotice, PageHeader } from "@/components/page-ui";
import { api, jsonBody } from "@/lib/api";
import type { AIJob, StudentSubject } from "@/lib/types";

type Level = "UNLEARNED" | "WEAK" | "DEVELOPING" | "PROFICIENT" | "MASTERED";
type Review = "DRAFT" | "PENDING_REVIEW" | "APPROVED" | "REJECTED" | "SUPERSEDED";
type WrongQuestion = {
  id: string;
  student_subject_id: string;
  student_name: string;
  subject_name: string;
  status: Review;
  mastery_status: Level;
  review_count: number;
  last_reviewed_at: string | null;
  version: number;
  current_version: {
    image_material_id: string | null;
    content: {
      question_text: string;
      source: string;
      difficulty: "BASIC" | "MEDIUM" | "ADVANCED";
      student_answer: string;
      correct_answer: string;
      error_reason: string;
      analysis: string;
      recognition_notes: string;
      knowledge_points: { knowledge_point_id: string | null; name: string }[];
    };
  };
};
type Recognition = { wrong_question: WrongQuestion; job: AIJob };

const levels: Record<Level, string> = {
  UNLEARNED: "未学习",
  WEAK: "薄弱",
  DEVELOPING: "一般",
  PROFICIENT: "熟练",
  MASTERED: "已掌握",
};
const statusLabels: Record<Review, string> = {
  DRAFT: "草稿",
  PENDING_REVIEW: "待审核",
  APPROVED: "已批准",
  REJECTED: "已驳回",
  SUPERSEDED: "已取代",
};

const blank = {
  question_text: "",
  source: "",
  difficulty: "MEDIUM" as const,
  student_answer: "",
  correct_answer: "",
  error_reason: "",
  analysis: "",
  knowledge_points: "",
};

export default function WrongQuestionsPage() {
  const client = useQueryClient();
  const subjects = useQuery({
    queryKey: ["student-subjects"],
    queryFn: () => api<StudentSubject[]>("/student-subjects"),
  });
  const questions = useQuery({
    queryKey: ["wrong-questions"],
    queryFn: () => api<WrongQuestion[]>("/wrong-questions"),
  });
  const [subjectId, setSubjectId] = useState("");
  const [form, setForm] = useState(blank);
  const [image, setImage] = useState<File>();
  const [jobId, setJobId] = useState<string>();
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
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
      void client.invalidateQueries({ queryKey: ["wrong-questions"] });
    }
  }, [client, job.data?.status]);

  async function refresh() {
    await client.invalidateQueries({ queryKey: ["wrong-questions"] });
  }
  async function createManual(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await api("/wrong-questions", {
        method: "POST",
        ...jsonBody({
          student_subject_id: subjectId,
          mastery_status: "WEAK",
          content: {
            schema_version: "1.0",
            ...form,
            source: form.source || "教师手工录入",
            knowledge_points: form.knowledge_points
              .split(/[，,\n]/)
              .map((name) => name.trim())
              .filter(Boolean)
              .map((name) => ({ knowledge_point_id: null, name })),
            recognition_notes: "",
          },
        }),
      });
      setForm(blank);
      await refresh();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }
  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!image) return;
    setBusy(true);
    setError(undefined);
    const body = new FormData();
    body.set("student_subject_id", subjectId);
    body.set("image", image);
    try {
      const result = await api<Recognition>("/wrong-questions/from-image", {
        method: "POST",
        body,
      });
      setJobId(result.job.id);
      setImage(undefined);
      await refresh();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }
  async function transition(item: WrongQuestion, action: "submit" | "approve" | "reject") {
    const reason = window.prompt(
      action === "approve" ? "请确认识别结果、答案和解析均已人工核对，并填写说明" : "操作说明",
    );
    if (!reason) return;
    try {
      await api(`/wrong-questions/${item.id}/${action}`, {
        method: "POST",
        ...jsonBody({ reason, version: item.version }),
      });
      await refresh();
    } catch (caught) {
      setError(caught);
    }
  }
  async function editDraft(item: WrongQuestion) {
    const content = item.current_version.content;
    const questionText = window.prompt("题目文字", content.question_text);
    if (!questionText) return;
    const correctAnswer = window.prompt("正确答案", content.correct_answer);
    if (correctAnswer === null) return;
    const errorReason = window.prompt("错误原因", content.error_reason);
    if (errorReason === null) return;
    const analysis = window.prompt("解析", content.analysis);
    if (analysis === null) return;
    const summary = window.prompt("版本修改说明", "教师核对并修正图片识别结果");
    if (!summary) return;
    try {
      await api(`/wrong-questions/${item.id}`, {
        method: "PUT",
        ...jsonBody({
          version: item.version,
          change_summary: summary,
          content: {
            ...content,
            question_text: questionText,
            correct_answer: correctAnswer,
            error_reason: errorReason,
            analysis,
          },
        }),
      });
      await refresh();
    } catch (caught) {
      setError(caught);
    }
  }
  async function review(item: WrongQuestion) {
    const result = window.prompt("复习结果：UNLEARNED / WEAK / DEVELOPING / PROFICIENT / MASTERED", item.mastery_status);
    if (!result || !(result in levels)) return;
    const notes = window.prompt("本次复习记录");
    if (!notes) return;
    try {
      await api(`/wrong-questions/${item.id}/reviews`, {
        method: "POST",
        ...jsonBody({ result_level: result, notes, version: item.version }),
      });
      await refresh();
    } catch (caught) {
      setError(caught);
    }
  }

  const visibleError =
    job.data?.status === "FAILED" ? new Error(job.data.error_message ?? "图片识别失败") : error;
  return (
    <>
      <PageHeader
        title="错题与复习"
        description="手工录入可直接形成正式错题；图片识别只生成草稿，必须由教师核对并批准。"
      />
      {visibleError ? <ErrorNotice error={visibleError} /> : null}
      <div className="grid gap-6 xl:grid-cols-2">
        <form className="card space-y-3" onSubmit={createManual}>
          <h2 className="text-lg font-semibold">手工录入正式错题</h2>
          <select className="field" required value={subjectId} onChange={(event) => setSubjectId(event.target.value)}>
            <option value="">选择学生与学科</option>
            {subjects.data?.map((item) => <option key={item.id} value={item.id}>{item.student_name} · {item.subject_name}</option>)}
          </select>
          <textarea className="field min-h-24" required placeholder="题目文字" value={form.question_text} onChange={(event) => setForm({ ...form, question_text: event.target.value })} />
          <div className="grid gap-3 md:grid-cols-2">
            <input className="field" placeholder="题目来源" value={form.source} onChange={(event) => setForm({ ...form, source: event.target.value })} />
            <input className="field" placeholder="知识点（逗号分隔）" value={form.knowledge_points} onChange={(event) => setForm({ ...form, knowledge_points: event.target.value })} />
            <input className="field" placeholder="学生答案" value={form.student_answer} onChange={(event) => setForm({ ...form, student_answer: event.target.value })} />
            <input className="field" required placeholder="正确答案" value={form.correct_answer} onChange={(event) => setForm({ ...form, correct_answer: event.target.value })} />
          </div>
          <textarea className="field" required placeholder="错误原因" value={form.error_reason} onChange={(event) => setForm({ ...form, error_reason: event.target.value })} />
          <textarea className="field min-h-24" required placeholder="解析" value={form.analysis} onChange={(event) => setForm({ ...form, analysis: event.target.value })} />
          <button className="button-primary w-full" disabled={busy}>保存正式错题</button>
        </form>
        <form className="card space-y-4" onSubmit={upload}>
          <h2 className="text-lg font-semibold">上传图片识别</h2>
          <p className="text-sm text-[var(--muted)]">仅支持 PNG/JPEG；默认 Mock 不产生费用，也不会读取真实题图。配置视觉提供商后才调用真实模型。</p>
          <select className="field" required value={subjectId} onChange={(event) => setSubjectId(event.target.value)}>
            <option value="">选择学生与学科</option>
            {subjects.data?.map((item) => <option key={item.id} value={item.id}>{item.student_name} · {item.subject_name}</option>)}
          </select>
          <input className="field" type="file" accept="image/png,image/jpeg" required onChange={(event) => setImage(event.target.files?.[0])} />
          <button className="button-primary w-full" disabled={busy || !image}>上传并生成识别草稿</button>
          {jobId ? <p className="text-sm">识别任务：{job.data?.status ?? "QUEUED"}</p> : null}
        </form>
      </div>
      <section className="mt-6 space-y-4">
        <h2 className="text-xl font-semibold">错题库</h2>
        {questions.data?.length ? questions.data.map((item) => (
          <article className="card" key={item.id}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div><p className="text-sm text-[var(--muted)]">{item.student_name} · {item.subject_name} · {statusLabels[item.status]}</p><h3 className="mt-2 font-semibold">{item.current_version.content.question_text}</h3></div>
              <span className="rounded-full bg-slate-100 px-3 py-1 text-sm">{levels[item.mastery_status]}</span>
            </div>
            <dl className="mt-4 grid gap-3 text-sm md:grid-cols-3"><div><dt className="text-[var(--muted)]">知识点</dt><dd>{item.current_version.content.knowledge_points.map((point) => point.name).join("、") || "待补充"}</dd></div><div><dt className="text-[var(--muted)]">错误原因</dt><dd>{item.current_version.content.error_reason || "待补充"}</dd></div><div><dt className="text-[var(--muted)]">复习次数</dt><dd>{item.review_count}</dd></div></dl>
            {item.current_version.image_material_id ? <a className="mt-4 inline-block text-sm underline" href={`/api/v1/uploaded-materials/${item.current_version.image_material_id}`} target="_blank">查看原图</a> : null}
            <div className="mt-4 flex flex-wrap gap-2">
              {item.status === "DRAFT" || item.status === "REJECTED" ? <><button className="button-secondary" onClick={() => editDraft(item)}>核对并修正</button><button className="button-secondary" onClick={() => transition(item, "submit")}>提交审核</button></> : null}
              {item.status === "PENDING_REVIEW" ? <><button className="button-primary" onClick={() => transition(item, "approve")}>批准</button><button className="button-danger" onClick={() => transition(item, "reject")}>驳回</button></> : null}
              {item.status === "APPROVED" ? <button className="button-secondary" onClick={() => review(item)}>记录复习</button> : null}
            </div>
          </article>
        )) : <EmptyState>还没有错题。可手工录入，或上传图片生成待审核草稿。</EmptyState>}
      </section>
    </>
  );
}
