"use client";

import { Archive, BookOpenText, PencilSimple, Plus, UserCircle } from "@phosphor-icons/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useMemo, useState } from "react";

import { useActionDialog } from "@/components/action-dialog";
import { EmptyState, ErrorNotice, PageHeader } from "@/components/page-ui";
import { api, jsonBody } from "@/lib/api";
import type { Student, StudentSubject, Subject } from "@/lib/types";

const blankStudent = {
  display_name: "",
  grade: "",
  region: "",
  school: "",
  learning_characteristics: "",
  guardian_requirements: "",
  notes: "",
};

export default function StudentsPage() {
  const client = useQueryClient();
  const openDialog = useActionDialog();
  const students = useQuery({ queryKey: ["students"], queryFn: () => api<Student[]>("/students") });
  const subjects = useQuery({ queryKey: ["subjects"], queryFn: () => api<Subject[]>("/subjects") });
  const links = useQuery({ queryKey: ["student-subjects"], queryFn: () => api<StudentSubject[]>("/student-subjects") });
  const [selectedId, setSelectedId] = useState<string>();
  const [form, setForm] = useState(blankStudent);
  const [subjectId, setSubjectId] = useState("");
  const [textbook, setTextbook] = useState("");
  const [error, setError] = useState<unknown>();
  const selected = students.data?.find((row) => row.id === selectedId) ?? students.data?.[0];
  const selectedLinks = useMemo(
    () => links.data?.filter((row) => row.student_id === selected?.id) ?? [],
    [links.data, selected?.id],
  );

  async function refresh() {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["students"] }),
      client.invalidateQueries({ queryKey: ["student-subjects"] }),
    ]);
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    setError(undefined);
    try {
      const payload = Object.fromEntries(Object.entries(form).map(([key, value]) => [key, value || null]));
      const row = await api<Student>("/students", { method: "POST", ...jsonBody(payload) });
      setForm(blankStudent);
      setSelectedId(row.id);
      await refresh();
    } catch (caught) {
      setError(caught);
    }
  }

  async function edit(row: Student) {
    const values = await openDialog({
      title: "编辑学生资料",
      description: "修改会保存到正式学生档案；学科基础与目标请在下方学科档案中单独编辑。",
      width: "wide",
      fields: [
        { name: "display_name", label: "学生姓名或代号", value: row.display_name, required: true, maxLength: 80 },
        { name: "grade", label: "年级", value: row.grade, placeholder: "例如：高二" },
        { name: "region", label: "地区", value: row.region, placeholder: "例如：广东省广州市" },
        { name: "school", label: "学校", value: row.school, placeholder: "可填写学校或班级" },
        { name: "learning_characteristics", label: "学习特点", value: row.learning_characteristics, type: "textarea", helper: "记录学习节奏、习惯、优势与需要关注的方面。" },
        { name: "guardian_requirements", label: "家长要求", value: row.guardian_requirements, type: "textarea" },
        { name: "notes", label: "教学注意事项", value: row.notes, type: "textarea" },
      ],
    });
    if (!values) return;
    setError(undefined);
    try {
      await api(`/students/${row.id}`, {
        method: "PUT",
        ...jsonBody({
          display_name: values.display_name,
          grade: values.grade || null,
          region: values.region || null,
          school: values.school || null,
          learning_characteristics: values.learning_characteristics || null,
          guardian_requirements: values.guardian_requirements || null,
          notes: values.notes || null,
          version: row.version,
        }),
      });
      await refresh();
    } catch (caught) {
      setError(caught);
    }
  }

  async function archive(row: Student) {
    const values = await openDialog({
      title: `归档“${row.display_name}”`,
      description: "归档后将不再出现在日常学生列表中。请先确认该学生没有计划中的课程。",
      tone: "danger",
      submitLabel: "确认归档",
      fields: [{ name: "reason", label: "归档原因", type: "textarea", required: true, placeholder: "请说明归档原因" }],
    });
    if (!values) return;
    try {
      await api(`/students/${row.id}/archive`, { method: "POST", ...jsonBody({ version: row.version, reason: values.reason }) });
      setSelectedId(undefined);
      await refresh();
    } catch (caught) {
      setError(caught);
    }
  }

  async function attach(event: FormEvent) {
    event.preventDefault();
    if (!selected || !subjectId) return;
    try {
      await api("/student-subjects", {
        method: "POST",
        ...jsonBody({ student_id: selected.id, subject_id: subjectId, textbook_version: textbook || null }),
      });
      setSubjectId("");
      setTextbook("");
      await refresh();
    } catch (caught) {
      setError(caught);
    }
  }

  async function editLink(row: StudentSubject) {
    const values = await openDialog({
      title: `编辑${row.subject_name}学科档案`,
      description: `${row.student_name} · ${row.subject_name}，该学科的教材、基础、目标和教学要求独立保存。`,
      width: "wide",
      fields: [
        { name: "textbook_version", label: "教材版本", value: row.textbook_version, placeholder: "例如：人教版 A 版" },
        { name: "current_foundation", label: "当前基础", value: row.current_foundation, type: "textarea" },
        { name: "overall_goal", label: "总目标", value: row.overall_goal, type: "textarea" },
        { name: "stage_goal", label: "阶段目标", value: row.stage_goal, type: "textarea" },
        { name: "teaching_requirements", label: "教学要求", value: row.teaching_requirements, type: "textarea" },
        { name: "attention_notes", label: "教学注意事项", value: row.attention_notes, type: "textarea" },
      ],
    });
    if (!values) return;
    try {
      await api(`/student-subjects/${row.id}`, {
        method: "PUT",
        ...jsonBody({
          textbook_version: values.textbook_version || null,
          current_foundation: values.current_foundation || null,
          overall_goal: values.overall_goal || null,
          stage_goal: values.stage_goal || null,
          teaching_requirements: values.teaching_requirements || null,
          attention_notes: values.attention_notes || null,
          version: row.version,
        }),
      });
      await refresh();
    } catch (caught) {
      setError(caught);
    }
  }

  return (
    <>
      <PageHeader title="学生档案" description="通用情况保存在学生档案；教材、基础、目标与要求按学科独立保存。" />
      {error ? <ErrorNotice error={error} /> : null}
      <div className="mt-5 grid gap-5 xl:grid-cols-[250px_minmax(0,1fr)_320px]">
        <section className="card h-fit p-0! overflow-hidden">
          <div className="flex items-center justify-between border-b border-[var(--rule-soft)] px-4 py-4">
            <div>
              <p className="font-semibold">学生列表</p>
              <p className="mt-1 text-xs text-[var(--muted)]">共 {students.data?.length ?? 0} 名</p>
            </div>
            <UserCircle size={24} color="var(--pine)" />
          </div>
          {students.isPending ? (
            <p className="p-4 text-sm text-[var(--muted)]">读取中…</p>
          ) : students.data?.length ? (
            <div className="divide-y divide-[var(--rule-soft)]">
              {students.data.map((row) => {
                const active = selected?.id === row.id;
                return (
                  <button
                    key={row.id}
                    className={`w-full border-l-2 px-4 py-3.5 text-left text-sm transition ${active ? "border-l-[var(--cinnabar)] bg-[var(--pine-wash)]" : "border-l-transparent hover:bg-[var(--sheet-muted)]"}`}
                    onClick={() => setSelectedId(row.id)}
                  >
                    <span className="block font-semibold">{row.display_name}</span>
                    <span className="mt-1 block text-xs text-[var(--muted)]">{row.grade || "年级未填写"}</span>
                  </button>
                );
              })}
            </div>
          ) : (
            <p className="p-4 text-sm text-[var(--muted)]">暂无学生</p>
          )}
        </section>

        <section>
          {selected ? (
            <div className="space-y-5">
              <article className="card">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <p className="text-xs font-semibold tracking-[0.14em] text-[var(--cinnabar)]">STUDENT PROFILE</p>
                    <h2 className="mt-2 font-[Songti_SC,SimSun,serif] text-3xl font-bold">{selected.display_name}</h2>
                    <p className="mt-2 text-sm text-[var(--muted)]">
                      {[selected.grade, selected.region, selected.school].filter(Boolean).join(" · ") || "尚未填写基础信息"}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button className="button-secondary" onClick={() => edit(selected)}>
                      <PencilSimple size={17} />编辑资料
                    </button>
                    <button className="button-danger" onClick={() => archive(selected)}>
                      <Archive size={17} />归档
                    </button>
                  </div>
                </div>
                <dl className="mt-6 grid gap-5 border-t border-[var(--rule-soft)] pt-5 text-sm md:grid-cols-2">
                  <div><dt className="text-xs font-semibold tracking-wide text-[var(--muted)]">学习特点</dt><dd className="mt-2 leading-7">{selected.learning_characteristics || "—"}</dd></div>
                  <div><dt className="text-xs font-semibold tracking-wide text-[var(--muted)]">家长要求</dt><dd className="mt-2 leading-7">{selected.guardian_requirements || "—"}</dd></div>
                  <div className="md:col-span-2"><dt className="text-xs font-semibold tracking-wide text-[var(--muted)]">教学注意事项</dt><dd className="mt-2 leading-7">{selected.notes || "—"}</dd></div>
                </dl>
              </article>

              <article className="card">
                <div className="flex items-center gap-2">
                  <BookOpenText size={21} color="var(--pine)" />
                  <h2 className="font-semibold">学科档案</h2>
                </div>
                {selectedLinks.length ? (
                  <div className="mt-4 divide-y divide-[var(--rule-soft)] border-y border-[var(--rule-soft)]">
                    {selectedLinks.map((row) => (
                      <div className="grid gap-3 py-4 md:grid-cols-[1fr_auto]" key={row.id}>
                        <div>
                          <strong>{row.subject_name}</strong>
                          <p className="mt-2 text-sm text-[var(--muted)]">教材：{row.textbook_version || "未填写"}</p>
                          <p className="mt-1 text-sm leading-6">阶段目标：{row.stage_goal || "未填写"}</p>
                        </div>
                        <button className="button-secondary self-start" onClick={() => editLink(row)}>
                          <PencilSimple size={16} />编辑
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="mt-4 text-sm text-[var(--muted)]">尚未关联学科。</p>
                )}
                <form className="mt-5 grid gap-3 md:grid-cols-3" onSubmit={attach}>
                  <select className="field" value={subjectId} onChange={(event) => setSubjectId(event.target.value)} required>
                    <option value="">选择学科</option>
                    {subjects.data
                      ?.filter((subject) => !selectedLinks.some((link) => link.subject_id === subject.id))
                      .map((subject) => <option key={subject.id} value={subject.id}>{subject.name}</option>)}
                  </select>
                  <input className="field" placeholder="教材版本（可选）" value={textbook} onChange={(event) => setTextbook(event.target.value)} />
                  <button className="button-primary"><Plus size={17} />关联学科</button>
                </form>
              </article>
            </div>
          ) : (
            <EmptyState>创建或选择一名学生。</EmptyState>
          )}
        </section>

        <aside className="card h-fit">
          <p className="text-xs font-semibold tracking-[0.14em] text-[var(--cinnabar)]">NEW STUDENT</p>
          <h2 className="mt-2 font-[Songti_SC,SimSun,serif] text-xl font-bold">新增学生</h2>
          <form className="mt-5 space-y-4" onSubmit={create}>
            {(["display_name", "grade", "region", "school"] as const).map((key) => (
              <label key={key}>
                <span className="label">{{ display_name: "姓名或代号", grade: "年级", region: "地区", school: "学校" }[key]}</span>
                <input className="field" required={key === "display_name"} value={form[key]} onChange={(event) => setForm({ ...form, [key]: event.target.value })} />
              </label>
            ))}
            <label><span className="label">学习特点</span><textarea className="field min-h-24" value={form.learning_characteristics} onChange={(event) => setForm({ ...form, learning_characteristics: event.target.value })} /></label>
            <button className="button-primary w-full"><Plus size={17} />创建学生</button>
          </form>
        </aside>
      </div>
    </>
  );
}
