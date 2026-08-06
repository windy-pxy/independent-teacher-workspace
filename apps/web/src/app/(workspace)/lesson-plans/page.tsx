"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { EmptyState, ErrorNotice, PageHeader } from "@/components/page-ui";
import { ApiError, api, apiBlob, jsonBody } from "@/lib/api";
import type {
  AIJob,
  DocumentVersion,
  Lesson,
  LessonDocument,
  LessonPlanContent,
  Material,
  PromptTemplate,
} from "@/lib/types";

const reviewLabels = {
  DRAFT: "草稿",
  PENDING_REVIEW: "待审核",
  APPROVED: "已批准",
  REJECTED: "已驳回",
  SUPERSEDED: "已取代",
} as const;

const sectionLabels: Record<string, string> = {
  objectives: "教学目标",
  schedule: "时间安排",
  knowledge_explanations: "知识点讲解",
  examples: "典型例题",
  in_class_exercises: "当堂练习",
  common_mistakes: "易错点",
  homework: "课后作业",
  teacher_notes: "教师注意事项",
};

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
        className="field min-h-28"
        value={value.join("\n")}
        onChange={(event) =>
          onChange(event.target.value.split("\n").filter((line) => line.trim()))
        }
      />
    </label>
  );
}

function QuestionEditor({
  title,
  questions,
  onChange,
}: {
  title: string;
  questions: NonNullable<LessonPlanContent["examples"]>;
  onChange: (value: NonNullable<LessonPlanContent["examples"]>) => void;
}) {
  return (
    <section className="card">
      <h2 className="font-semibold">{title}</h2>
      <div className="mt-4 space-y-4">
        {questions.map((question, index) => (
          <fieldset
            key={question.id}
            className="rounded-xl border border-[var(--border)] p-4"
          >
            <legend className="px-2 text-sm font-medium">题目 {index + 1}</legend>
            {(["stem_markdown", "answer_markdown", "analysis_markdown"] as const).map(
              (field) => (
                <label className="mt-3 block" key={field}>
                  <span className="label">
                    {field === "stem_markdown"
                      ? "题干"
                      : field === "answer_markdown"
                        ? "答案"
                        : "解析"}
                  </span>
                  <textarea
                    className="field min-h-24"
                    value={question[field]}
                    onChange={(event) => {
                      const next = [...questions];
                      next[index] = { ...question, [field]: event.target.value };
                      onChange(next);
                    }}
                  />
                </label>
              ),
            )}
          </fieldset>
        ))}
      </div>
    </section>
  );
}

export default function LessonPlansPage() {
  const searchParams = useSearchParams();
  const client = useQueryClient();
  const lessons = useQuery({
    queryKey: ["lessons", "all"],
    queryFn: () => api<Lesson[]>("/lessons"),
  });
  const templates = useQuery({
    queryKey: ["prompt-templates"],
    queryFn: () => api<PromptTemplate[]>("/prompt-templates"),
  });
  const [lessonId, setLessonId] = useState(searchParams.get("lesson") ?? "");
  const selectedLesson = lessons.data?.find((lesson) => lesson.id === lessonId);
  const materials = useQuery({
    queryKey: ["materials", selectedLesson?.student_subject_id],
    queryFn: () =>
      api<Material[]>(
        `/materials?student_subject_id=${encodeURIComponent(selectedLesson!.student_subject_id)}`,
      ),
    enabled: Boolean(selectedLesson),
  });
  const [templateId, setTemplateId] = useState("");
  const [extraRequirements, setExtraRequirements] = useState("");
  const [materialIds, setMaterialIds] = useState<string[]>([]);
  const [jobId, setJobId] = useState<string>();
  const [downloading, setDownloading] = useState(false);
  const [draftEdit, setDraftEdit] = useState<{
    version: number;
    content: LessonPlanContent;
  }>();
  const [error, setError] = useState<unknown>();
  const document = useQuery({
    queryKey: ["lesson-document", lessonId],
    queryFn: () => api<LessonDocument>(`/lessons/${lessonId}/document`),
    enabled: Boolean(lessonId),
    retry: (count, caught) =>
      caught instanceof ApiError && caught.status === 404 ? false : count < 2,
  });
  const job = useQuery({
    queryKey: ["ai-job", jobId],
    queryFn: () => api<AIJob>(`/ai-jobs/${jobId}`),
    enabled: Boolean(jobId),
    refetchInterval: (query) =>
      ["SUCCEEDED", "FAILED", "CANCELED"].includes(query.state.data?.status ?? "")
        ? false
        : 1000,
  });
  const versions = useQuery({
    queryKey: ["document-versions", document.data?.id],
    queryFn: () =>
      api<DocumentVersion[]>(`/lesson-documents/${document.data!.id}/versions`),
    enabled: Boolean(document.data),
  });

  const draft =
    draftEdit && draftEdit.version === document.data?.current_version_number
      ? draftEdit.content
      : document.data?.current_version.content;
  const setDraft = (content: LessonPlanContent) => {
    if (document.data) {
      setDraftEdit({ version: document.data.current_version_number, content });
    }
  };
  const displayedError =
    error ??
    (job.data?.status === "FAILED"
      ? new Error(job.data.error_message ?? "生成失败")
      : undefined);

  useEffect(() => {
    if (job.data?.status === "SUCCEEDED") {
      void client.invalidateQueries({ queryKey: ["lesson-document", lessonId] });
      void client.invalidateQueries({ queryKey: ["document-versions"] });
    }
  }, [client, job.data, lessonId]);

  async function generate(event: FormEvent) {
    event.preventDefault();
    if (!lessonId) return;
    try {
      setError(undefined);
      const queued = await api<AIJob>(`/lessons/${lessonId}/documents/generate`, {
        method: "POST",
        ...jsonBody({
          template_id: templateId || null,
          extra_requirements: extraRequirements || null,
          material_ids: materialIds,
        }),
      });
      setJobId(queued.id);
    } catch (caught) {
      setError(caught);
    }
  }

  async function save() {
    if (!document.data || !draft) return;
    const summary = window.prompt("请输入本次编辑说明", "教师修改结构化教案");
    if (!summary) return;
    try {
      await api(`/lesson-documents/${document.data.id}`, {
        method: "PUT",
        ...jsonBody({ content: draft, change_summary: summary, version: document.data.version }),
      });
      await client.invalidateQueries({ queryKey: ["lesson-document", lessonId] });
      await client.invalidateQueries({ queryKey: ["document-versions"] });
    } catch (caught) {
      setError(caught);
    }
  }

  async function review(action: "submit" | "approve" | "reject") {
    if (!document.data) return;
    const reason = window.prompt(
      action === "submit" ? "提交审核说明" : action === "approve" ? "批准说明" : "驳回原因",
    );
    if (!reason) return;
    try {
      await api(`/lesson-documents/${document.data.id}/${action}`, {
        method: "POST",
        ...jsonBody({ reason, version: document.data.version }),
      });
      await client.invalidateQueries({ queryKey: ["lesson-document", lessonId] });
    } catch (caught) {
      setError(caught);
    }
  }

  async function regenerate(section: string) {
    if (!document.data) return;
    const instructions = window.prompt(`重新生成“${sectionLabels[section]}”的要求`);
    if (!instructions) return;
    try {
      const queued = await api<AIJob>(
        `/lesson-documents/${document.data.id}/regenerate-section`,
        {
          method: "POST",
          ...jsonBody({ section, instructions, version: document.data.version }),
        },
      );
      setJobId(queued.id);
    } catch (caught) {
      setError(caught);
    }
  }

  async function downloadWord() {
    if (!document.data) return;
    try {
      setDownloading(true);
      const result = await apiBlob(
        `/lesson-documents/${document.data.id}/export.docx`,
        { method: "POST" },
      );
      const url = URL.createObjectURL(result.blob);
      const link = window.document.createElement("a");
      link.href = url;
      link.download = result.filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setError(caught);
    } finally {
      setDownloading(false);
    }
  }

  return (
    <>
      <PageHeader
        title="AI 教案"
        description="结构化章节编辑、局部重新生成、人工审核、版本历史和教师版 Word 导出。开发环境默认使用 Mock，不产生模型费用。"
      />
      {displayedError ? <ErrorNotice error={displayedError} /> : null}
      <form className="card mt-4 grid gap-3 lg:grid-cols-[1fr_1fr_2fr_auto]" onSubmit={generate}>
        <select className="field" value={lessonId} onChange={(event) => { setLessonId(event.target.value); setMaterialIds([]); }} required>
          <option value="">选择课程</option>
          {lessons.data?.map((lesson) => (
            <option value={lesson.id} key={lesson.id}>
              {lesson.student_name} · {lesson.subject_name} · {lesson.theme}
            </option>
          ))}
        </select>
        <select className="field" value={templateId} onChange={(event) => setTemplateId(event.target.value)}>
          <option value="">自动选择通用模板</option>
          {templates.data?.map((template) => (
            <option value={template.id} key={template.id}>
              {template.grade_band ? `${template.grade_band} · ` : ""}{template.name}
            </option>
          ))}
        </select>
        <input
          className="field"
          placeholder="额外要求，例如：先复习单位换算"
          value={extraRequirements}
          onChange={(event) => setExtraRequirements(event.target.value)}
        />
        <button className="button-primary" disabled={!lessonId || job.isFetching}>
          {job.isFetching ? "生成中…" : document.data ? "生成新草稿" : "生成教案"}
        </button>
        {lessonId ? (
          <fieldset className="rounded-xl border border-[var(--border)] p-3 lg:col-span-4">
            <legend className="px-2 text-sm font-medium">参考资料（最多选择 10 份）</legend>
            {materials.data?.length ? (
              <div className="flex flex-wrap gap-3">
                {materials.data.map((material) => (
                  <label className="flex items-center gap-2 text-sm" key={material.id}>
                    <input
                      type="checkbox"
                      checked={materialIds.includes(material.id)}
                      disabled={!materialIds.includes(material.id) && materialIds.length >= 10}
                      onChange={(event) => setMaterialIds((current) => event.target.checked ? [...current, material.id] : current.filter((id) => id !== material.id))}
                    />
                    <span>{material.display_name}</span>
                  </label>
                ))}
              </div>
            ) : (
              <p className="text-sm text-[var(--muted)]">该学生学科暂无资料，可先到“资料库”上传。</p>
            )}
          </fieldset>
        ) : null}
      </form>

      {!lessonId ? (
        <EmptyState>请先选择一节课程。</EmptyState>
      ) : document.isPending ? (
        <EmptyState>正在读取教案…</EmptyState>
      ) : !document.data || !draft ? (
        <EmptyState>该课程尚无教案，填写要求后点击“生成教案”。</EmptyState>
      ) : (
        <div className="mt-5 grid gap-6 xl:grid-cols-[1fr_260px]">
          <div className="space-y-5">
            <section className="card flex flex-wrap items-center justify-between gap-3">
              <div>
                <span className="badge">{reviewLabels[document.data.status]}</span>
                <h2 className="mt-2 text-xl font-semibold">{document.data.title}</h2>
                <p className="mt-1 text-sm text-[var(--muted)]">
                  当前内容版本 {document.data.current_version_number}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button className="button-secondary" type="button" onClick={save}>保存新版本</button>
                {document.data.status === "DRAFT" || document.data.status === "REJECTED" ? (
                  <button className="button-primary" type="button" onClick={() => review("submit")}>提交审核</button>
                ) : null}
                {document.data.status === "PENDING_REVIEW" ? (
                  <>
                    <button className="button-primary" type="button" onClick={() => review("approve")}>批准</button>
                    <button className="button-danger" type="button" onClick={() => review("reject")}>驳回</button>
                  </>
                ) : null}
                {document.data.approved_version_number ? (
                  <button className="button-secondary" type="button" disabled={downloading} onClick={downloadWord}>
                    {downloading ? "正在生成…" : "下载 Word"}
                  </button>
                ) : null}
              </div>
            </section>

            <section className="card">
              <div className="mb-4 flex justify-between gap-3"><h2 className="font-semibold">教学目标</h2><button className="button-secondary" onClick={() => regenerate("objectives")}>局部生成</button></div>
              <LinesEditor label="教学目标" value={draft.objectives} onChange={(objectives) => setDraft({ ...draft, objectives })} />
            </section>

            <section className="card">
              <div className="mb-4 flex justify-between gap-3"><h2 className="font-semibold">时间安排</h2><button className="button-secondary" onClick={() => regenerate("schedule")}>局部生成</button></div>
              <div className="space-y-3">{draft.schedule.map((block, index) => <div className="grid gap-3 rounded-xl border border-[var(--border)] p-4 md:grid-cols-[100px_1fr_2fr]" key={`${block.title}-${index}`}><input className="field" type="number" value={block.minutes} onChange={(event) => { const schedule=[...draft.schedule]; schedule[index]={...block,minutes:Number(event.target.value)}; setDraft({...draft,schedule}); }} /><input className="field" value={block.title} onChange={(event) => { const schedule=[...draft.schedule]; schedule[index]={...block,title:event.target.value}; setDraft({...draft,schedule}); }} /><textarea className="field" value={block.activities_markdown} onChange={(event) => { const schedule=[...draft.schedule]; schedule[index]={...block,activities_markdown:event.target.value}; setDraft({...draft,schedule}); }} /></div>)}</div>
            </section>

            <section className="card">
              <div className="mb-4 flex justify-between gap-3"><h2 className="font-semibold">知识点讲解</h2><button className="button-secondary" onClick={() => regenerate("knowledge_explanations")}>局部生成</button></div>
              <div className="space-y-3">{draft.knowledge_explanations.map((section,index) => <div className="rounded-xl border border-[var(--border)] p-4" key={section.id}><input className="field" value={section.title} onChange={(event) => { const rows=[...draft.knowledge_explanations]; rows[index]={...section,title:event.target.value}; setDraft({...draft,knowledge_explanations:rows}); }} /><textarea className="field mt-3 min-h-36" value={section.body_markdown} onChange={(event) => { const rows=[...draft.knowledge_explanations]; rows[index]={...section,body_markdown:event.target.value}; setDraft({...draft,knowledge_explanations:rows}); }} /></div>)}</div>
            </section>

            <QuestionEditor title="典型例题" questions={draft.examples ?? []} onChange={(examples) => setDraft({...draft,examples})} />
            <QuestionEditor title="当堂练习" questions={draft.in_class_exercises ?? []} onChange={(in_class_exercises) => setDraft({...draft,in_class_exercises})} />
            <section className="card"><div className="mb-4 flex justify-between gap-3"><h2 className="font-semibold">易错点</h2><button className="button-secondary" onClick={() => regenerate("common_mistakes")}>局部生成</button></div><LinesEditor label="易错点" value={draft.common_mistakes ?? []} onChange={(common_mistakes) => setDraft({...draft,common_mistakes})} /></section>
            <QuestionEditor title="课后作业" questions={draft.homework ?? []} onChange={(homework) => setDraft({...draft,homework})} />
            <section className="card"><div className="mb-4 flex justify-between gap-3"><h2 className="font-semibold">教师注意事项</h2><button className="button-secondary" onClick={() => regenerate("teacher_notes")}>局部生成</button></div><LinesEditor label="教师注意事项" value={draft.teacher_notes ?? []} onChange={(teacher_notes) => setDraft({...draft,teacher_notes})} /></section>
          </div>
          <aside className="card h-fit">
            <h2 className="font-semibold">版本历史</h2>
            <ol className="mt-4 space-y-3">{versions.data?.map((version) => <li className="border-l-2 border-slate-200 pl-3 text-sm" key={version.id}><strong>版本 {version.version_number}</strong><p>{version.change_summary}</p><span className="text-xs text-[var(--muted)]">{version.source}</span></li>)}</ol>
          </aside>
        </div>
      )}
    </>
  );
}
