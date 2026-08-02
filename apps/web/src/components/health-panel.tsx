"use client";

import { useEffect, useState } from "react";

type HealthResponse = {
  status: "ok" | "unavailable";
  service: string;
  database?: string;
};

export function HealthPanel() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/health/ready", { signal: controller.signal, cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error("API not ready");
        setHealth((await response.json()) as HealthResponse);
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) setFailed(true);
      });
    return () => controller.abort();
  }, []);

  const ready = health?.status === "ok";
  return (
    <aside aria-label="系统状态" className="rounded-2xl border border-[var(--border)] bg-white p-6">
      <div className="flex items-center gap-3">
        <span className={`h-3 w-3 rounded-full ${ready ? "bg-emerald-600" : failed ? "bg-red-500" : "animate-pulse bg-amber-500"}`} />
        <h2 className="m-0 text-lg font-semibold">系统状态</h2>
      </div>
      <p role="status" className="mb-0 mt-4 text-sm leading-6 text-[var(--muted)]">
        {ready ? "Web、API 与数据库连接正常。" : failed ? "API 或数据库尚未就绪。请检查后端服务。" : "正在检查 API 与数据库…"}
      </p>
    </aside>
  );
}
