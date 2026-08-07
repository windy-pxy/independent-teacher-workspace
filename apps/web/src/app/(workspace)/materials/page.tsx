"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";

import { useActionDialog } from "@/components/action-dialog";
import { EmptyState, ErrorNotice, PageHeader } from "@/components/page-ui";
import { api, jsonBody } from "@/lib/api";
import type { Material, StudentSubject } from "@/lib/types";

const purposeLabels = {
  TEACHING_MATERIAL: "教材与讲义",
  EXAM_PAPER: "试卷",
  OLD_LESSON_PLAN: "旧教案",
  OTHER_REFERENCE: "其他参考资料",
} as const;

export default function MaterialsPage() {
  const client = useQueryClient();
  const openDialog = useActionDialog();
  const subjects = useQuery({
    queryKey: ["student-subjects"],
    queryFn: () => api<StudentSubject[]>("/student-subjects"),
  });
  const materials = useQuery({
    queryKey: ["materials"],
    queryFn: () => api<Material[]>("/materials"),
  });
  const [studentSubjectId, setStudentSubjectId] = useState("");
  const [purpose, setPurpose] = useState<keyof typeof purposeLabels>("TEACHING_MATERIAL");
  const [file, setFile] = useState<File>();
  const [fileKey, setFileKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!studentSubjectId || !file) return;
    const body = new FormData();
    body.set("student_subject_id", studentSubjectId);
    body.set("purpose", purpose);
    body.set("file", file);
    try {
      setBusy(true);
      setError(undefined);
      await api<Material>("/materials", { method: "POST", body });
      setFile(undefined);
      setFileKey((value) => value + 1);
      await client.invalidateQueries({ queryKey: ["materials"] });
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  async function archive(material: Material) {
    const values = await openDialog({ title: `归档“${material.display_name}”`, tone: "danger", submitLabel: "确认归档", fields: [{ name: "reason", label: "归档原因", type: "textarea", required: true }] });
    if (!values) return;
    try {
      setError(undefined);
      await api(`/materials/${material.id}/archive`, {
        method: "POST",
        ...jsonBody({ version: material.version, reason: values.reason }),
      });
      await client.invalidateQueries({ queryKey: ["materials"] });
    } catch (caught) {
      setError(caught);
    }
  }

  return (
    <>
      <PageHeader
        title="资料库"
        description="安全保存教材、试卷和旧教案，提取可审核的文本片段，并在生成教案时由教师明确选用。"
      />
      {error ? <ErrorNotice error={error} /> : null}
      <form className="card mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-[1.2fr_1fr_1.5fr_auto]" onSubmit={upload}>
        <select className="field" value={studentSubjectId} onChange={(event) => setStudentSubjectId(event.target.value)} required>
          <option value="">选择学生与学科</option>
          {subjects.data?.map((item) => (
            <option key={item.id} value={item.id}>{item.student_name} · {item.subject_name}</option>
          ))}
        </select>
        <select className="field" value={purpose} onChange={(event) => setPurpose(event.target.value as keyof typeof purposeLabels)}>
          {Object.entries(purposeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
        <input key={fileKey} className="field" type="file" accept=".pdf,.docx,.txt" onChange={(event) => setFile(event.target.files?.[0])} required />
        <button className="button-primary" disabled={busy || !studentSubjectId || !file}>{busy ? "正在提取…" : "上传资料"}</button>
        <p className="text-xs text-[var(--muted)] md:col-span-2 xl:col-span-4">支持 PDF、DOCX、UTF-8 TXT；扫描版或加密 PDF 暂不支持。文件先完成类型、大小和结构校验，再进入资料库。</p>
      </form>

      <section className="mt-5 grid gap-4 lg:grid-cols-2">
        {materials.data?.map((material) => (
          <article className="card" key={material.id}>
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <span className="badge">{purposeLabels[material.purpose]}</span>
                <h2 className="mt-2 truncate font-semibold" title={material.display_name}>{material.display_name}</h2>
                <p className="mt-1 text-sm text-[var(--muted)]">{material.student_name} · {material.subject_name}</p>
              </div>
              <button className="button-danger" type="button" onClick={() => archive(material)}>归档</button>
            </div>
            <dl className="mt-4 grid grid-cols-3 gap-3 text-sm">
              <div><dt className="text-[var(--muted)]">文件大小</dt><dd className="mt-1">{(material.size_bytes / 1024).toFixed(1)} KB</dd></div>
              <div><dt className="text-[var(--muted)]">文本片段</dt><dd className="mt-1">{material.chunk_count} 段</dd></div>
              <div><dt className="text-[var(--muted)]">提取字符</dt><dd className="mt-1">{material.extracted_chars}</dd></div>
            </dl>
            <a className="button-secondary mt-4" href={`/api/v1/materials/${material.id}/download`}>下载原文件</a>
          </article>
        ))}
      </section>
      {!materials.isPending && !materials.data?.length ? <EmptyState>尚未上传资料。</EmptyState> : null}
    </>
  );
}
