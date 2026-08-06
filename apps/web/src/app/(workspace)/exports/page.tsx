"use client";

import { useState } from "react";

import { ErrorNotice, PageHeader } from "@/components/page-ui";
import { apiBlob } from "@/lib/api";

export default function ExportsPage() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();

  async function downloadObsidian() {
    try {
      setBusy(true);
      setError(undefined);
      const result = await apiBlob("/exports/obsidian.zip", { method: "POST" });
      const url = URL.createObjectURL(result.blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = result.filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="导出与 Obsidian"
        description="生成 PostgreSQL 正式数据的单向 Markdown 快照，用于离线查阅和版本归档。"
      />
      {error ? <ErrorNotice error={error} /> : null}
      <section className="card mt-4 max-w-3xl">
        <h2 className="text-lg font-semibold">Obsidian Vault 快照</h2>
        <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
          ZIP 包含学生档案、各学科教学计划、知识点掌握度、课程、已批准教案、已批准反馈和正式错题。它不会包含密码、API 密钥、会话、日志、收费明细或原始上传附件。
        </p>
        <ol className="mt-4 list-decimal space-y-2 pl-5 text-sm">
          <li>下载 ZIP 并解压到一个新文件夹。</li>
          <li>在 Obsidian 中选择“打开文件夹作为仓库”。</li>
          <li>以后重新导出时保留为新的时间点快照，不要覆盖后再期待自动同步。</li>
        </ol>
        <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          Obsidian 中的修改不会写回工作台；PostgreSQL 始终是唯一正式数据源。ZIP 含学生教学信息，请只保存在你控制的设备和加密备份中。
        </div>
        <button className="button-primary mt-5" type="button" disabled={busy} onClick={downloadObsidian}>
          {busy ? "正在生成快照…" : "下载 Obsidian 快照"}
        </button>
      </section>
    </>
  );
}
