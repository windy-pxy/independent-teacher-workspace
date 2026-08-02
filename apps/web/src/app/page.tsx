import { HealthPanel } from "@/components/health-panel";

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-5xl items-center px-6 py-16">
      <section className="grid w-full gap-8 rounded-3xl border border-[var(--border)] bg-[var(--card)] p-8 shadow-sm md:grid-cols-[1.3fr_0.7fr] md:p-12">
        <div>
          <p className="mb-4 text-sm font-semibold tracking-[0.22em] text-[var(--accent)]">PHASE 0 · 工程骨架</p>
          <h1 className="m-0 text-4xl font-semibold tracking-tight md:text-5xl">独立教师工作台</h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-[var(--muted)]">
            当前版本只提供可验证的系统基础。学生档案、课程、教案与反馈将在后续阶段按审核闭环逐步开放。
          </p>
        </div>
        <HealthPanel />
      </section>
    </main>
  );
}
