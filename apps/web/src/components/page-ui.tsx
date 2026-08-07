export function PageHeader({ title, description }: { title: string; description: string }) {
  return (
    <header className="mb-6">
      <p className="page-kicker">TEACHING WORKSPACE</p>
      <h1 className="page-title">{title}</h1>
      <p className="page-description">{description}</p>
    </header>
  );
}

export function EmptyState({ children }: { children: React.ReactNode }) {
  return <div className="card py-10 text-center text-sm text-[var(--muted)]">{children}</div>;
}

export function ErrorNotice({ error }: { error: unknown }) {
  return <p role="alert" className="notice-error">{error instanceof Error ? error.message : "操作失败"}</p>;
}
