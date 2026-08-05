"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useMemo, useState } from "react";

import { EmptyState, ErrorNotice, PageHeader } from "@/components/page-ui";
import { api, apiBlob, jsonBody } from "@/lib/api";

type PaymentStatus = "UNPAID" | "PARTIAL" | "PAID" | "OVERPAID";
type BillingLesson = {
  lesson_id: string;
  student_subject_id: string;
  student_name: string;
  subject_name: string;
  scheduled_start: string;
  lesson_status: string;
  theme: string;
  planned_minutes: number;
  actual_minutes: number | null;
  unit_price_cents: number;
  receivable_cents: number;
  receivable_is_overridden: boolean;
  receivable_override_reason: string | null;
  allocated_cents: number;
  outstanding_cents: number;
  payment_status: PaymentStatus;
  version: number;
};
type StudentSummary = {
  student_id: string;
  student_name: string;
  lesson_count: number;
  completed_minutes: number;
  receivable_cents: number;
  allocated_cents: number;
  outstanding_cents: number;
};
type BillingSummary = {
  period_start: string;
  period_end: string;
  lesson_count: number;
  completed_minutes: number;
  receivable_cents: number;
  allocated_cents: number;
  outstanding_cents: number;
  received_cents: number;
  students: StudentSummary[];
};
type Payment = {
  id: string;
  amount_cents: number;
  paid_at: string;
  method: string;
  reference: string | null;
  notes: string | null;
  voided_at: string | null;
  void_reason: string | null;
  allocated_cents: number;
  unallocated_cents: number;
  allocations: { id: string; lesson_id: string; amount_cents: number }[];
  version: number;
};

const money = new Intl.NumberFormat("zh-CN", {
  style: "currency",
  currency: "CNY",
});
const dateTime = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  month: "numeric",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});
const statusLabels: Record<PaymentStatus, string> = {
  UNPAID: "未付款",
  PARTIAL: "部分付款",
  PAID: "已付清",
  OVERPAID: "超额付款",
};

function centsToYuan(cents: number): string {
  return (cents / 100).toFixed(2);
}

function yuanToCents(value: string): number | null {
  const match = value.trim().match(/^(\d+)(?:\.(\d{1,2}))?$/);
  if (!match) return null;
  return Number(match[1]) * 100 + Number((match[2] ?? "").padEnd(2, "0"));
}

function localInputNow(): string {
  const now = new Date(Date.now() - new Date().getTimezoneOffset() * 60_000);
  return now.toISOString().slice(0, 16);
}

export default function BillingPage() {
  const client = useQueryClient();
  const [month, setMonth] = useState(() => new Date());
  const [periodMode, setPeriodMode] = useState<"month" | "week">("month");
  const mondayOffset = (month.getDay() + 6) % 7;
  const periodStart = periodMode === "month"
    ? new Date(month.getFullYear(), month.getMonth(), 1)
    : new Date(month.getFullYear(), month.getMonth(), month.getDate() - mondayOffset);
  const periodEnd = periodMode === "month"
    ? new Date(month.getFullYear(), month.getMonth() + 1, 1)
    : new Date(periodStart.getFullYear(), periodStart.getMonth(), periodStart.getDate() + 7);
  const period = `date_from=${encodeURIComponent(periodStart.toISOString())}&date_to=${encodeURIComponent(periodEnd.toISOString())}`;
  const periodKey = `${periodMode}-${periodStart.toISOString()}`;
  const periodLabel = periodMode === "month" ? "本月" : "本周";
  const lessons = useQuery({
    queryKey: ["billing-lessons", periodKey],
    queryFn: () => api<BillingLesson[]>(`/billing/lessons?${period}`),
  });
  const summary = useQuery({
    queryKey: ["billing-summary", periodKey],
    queryFn: () => api<BillingSummary>(`/billing/summary?${period}`),
  });
  const payments = useQuery({
    queryKey: ["payments", periodKey],
    queryFn: () => api<Payment[]>(`/payments?${period}&include_voided=true`),
  });
  const [paidAt, setPaidAt] = useState(localInputNow);
  const [method, setMethod] = useState("微信");
  const [amountYuan, setAmountYuan] = useState("");
  const [reference, setReference] = useState("");
  const [notes, setNotes] = useState("");
  const [allocations, setAllocations] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const outstanding = useMemo(
    () =>
      (lessons.data ?? []).filter(
        (item) => item.outstanding_cents > 0 && item.lesson_status !== "RESCHEDULED",
      ),
    [lessons.data],
  );

  async function refresh() {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["billing-lessons"] }),
      client.invalidateQueries({ queryKey: ["billing-summary"] }),
      client.invalidateQueries({ queryKey: ["payments"] }),
      client.invalidateQueries({ queryKey: ["dashboard"] }),
      client.invalidateQueries({ queryKey: ["lessons"] }),
    ]);
  }
  function toggleAllocation(item: BillingLesson, checked: boolean) {
    const next = { ...allocations };
    if (checked) next[item.lesson_id] = centsToYuan(item.outstanding_cents);
    else delete next[item.lesson_id];
    setAllocations(next);
    const total = Object.values(next).reduce(
      (sum, value) => sum + (yuanToCents(value) ?? 0),
      0,
    );
    setAmountYuan(centsToYuan(total));
  }
  async function createPayment(event: FormEvent) {
    event.preventDefault();
    const amount = yuanToCents(amountYuan);
    if (!amount || amount <= 0) {
      setError(new Error("请输入有效的收款金额，最多保留两位小数"));
      return;
    }
    const parsedAllocations = Object.entries(allocations).map(([lessonId, value]) => ({
      lesson_id: lessonId,
      amount_cents: yuanToCents(value),
    }));
    if (parsedAllocations.some((item) => !item.amount_cents || item.amount_cents <= 0)) {
      setError(new Error("分摊金额必须大于零且最多保留两位小数"));
      return;
    }
    setBusy(true);
    setError(undefined);
    try {
      await api("/payments", {
        method: "POST",
        ...jsonBody({
          amount_cents: amount,
          paid_at: new Date(paidAt).toISOString(),
          method,
          reference: reference || null,
          notes: notes || null,
          allocations: parsedAllocations,
        }),
      });
      setAmountYuan("");
      setReference("");
      setNotes("");
      setAllocations({});
      await refresh();
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }
  async function updatePricing(item: BillingLesson) {
    const value = window.prompt("每小时单价（元）", centsToYuan(item.unit_price_cents));
    if (value === null) return;
    const cents = yuanToCents(value);
    if (cents === null) return setError(new Error("单价格式不正确"));
    const reason = window.prompt("调整单价原因");
    if (!reason) return;
    try {
      await api(`/lessons/${item.lesson_id}/pricing`, {
        method: "PUT",
        ...jsonBody({ unit_price_cents: cents, reason, version: item.version }),
      });
      await refresh();
    } catch (caught) {
      setError(caught);
    }
  }
  async function overrideReceivable(item: BillingLesson) {
    const value = window.prompt("人工应收金额（元）", centsToYuan(item.receivable_cents));
    if (value === null) return;
    const cents = yuanToCents(value);
    if (cents === null) return setError(new Error("应收金额格式不正确"));
    const reason = window.prompt("必须填写覆盖原因");
    if (!reason) return;
    try {
      await api(`/lessons/${item.lesson_id}/receivable-override`, {
        method: "POST",
        ...jsonBody({ receivable_cents: cents, reason, version: item.version }),
      });
      await refresh();
    } catch (caught) {
      setError(caught);
    }
  }
  async function resetReceivable(item: BillingLesson) {
    const reason = window.prompt("恢复自动计算的原因");
    if (!reason) return;
    try {
      await api(`/lessons/${item.lesson_id}/receivable-reset`, {
        method: "POST",
        ...jsonBody({ reason, version: item.version }),
      });
      await refresh();
    } catch (caught) {
      setError(caught);
    }
  }
  async function voidPayment(item: Payment) {
    const reason = window.prompt("作废后相关分摊不再计入已收，请填写原因");
    if (!reason) return;
    try {
      await api(`/payments/${item.id}/void`, {
        method: "POST",
        ...jsonBody({ reason, version: item.version }),
      });
      await refresh();
    } catch (caught) {
      setError(caught);
    }
  }
  async function addAllocation(payment: Payment) {
    if (!outstanding.length) return;
    const options = outstanding
      .map((item, index) => `${index + 1}. ${item.student_name} · ${item.theme}（未收 ${money.format(item.outstanding_cents / 100)}）`)
      .join("\n");
    const selected = window.prompt(`选择课程序号：\n${options}`, "1");
    if (!selected) return;
    const lesson = outstanding[Number(selected) - 1];
    if (!lesson) return setError(new Error("课程序号无效"));
    if (payment.allocations.some((item) => item.lesson_id === lesson.lesson_id)) {
      return setError(new Error("该笔收款已分摊到这节课程"));
    }
    const value = window.prompt(
      "分摊金额（元）",
      centsToYuan(Math.min(payment.unallocated_cents, lesson.outstanding_cents)),
    );
    if (!value) return;
    const cents = yuanToCents(value);
    if (!cents) return setError(new Error("分摊金额格式不正确"));
    try {
      await api(`/payments/${payment.id}/allocations`, {
        method: "POST",
        ...jsonBody({ lesson_id: lesson.lesson_id, amount_cents: cents, version: payment.version }),
      });
      await refresh();
    } catch (caught) {
      setError(caught);
    }
  }
  async function download(kind: "csv" | "xlsx") {
    try {
      const result = await apiBlob(`/billing/export.${kind}?${period}`);
      const url = URL.createObjectURL(result.blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = result.filename;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setError(caught);
    }
  }
  function movePeriod(direction: -1 | 1) {
    setMonth(
      periodMode === "month"
        ? new Date(month.getFullYear(), month.getMonth() + direction, 1)
        : new Date(month.getFullYear(), month.getMonth(), month.getDate() + direction * 7),
    );
  }

  return <>
    <PageHeader title="课时与收费" description="按实际分钟结算应收，记录真实到账并分摊到课程；付款状态由金额实时计算，不接入在线支付。" />
    {error ? <ErrorNotice error={error} /> : null}
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap items-center gap-2"><button className={periodMode === "month" ? "button-primary" : "button-secondary"} onClick={() => setPeriodMode("month")}>按月</button><button className={periodMode === "week" ? "button-primary" : "button-secondary"} onClick={() => setPeriodMode("week")}>按周</button><button className="button-secondary" onClick={() => movePeriod(-1)}>上一{periodMode === "month" ? "月" : "周"}</button><strong>{periodMode === "month" ? `${periodStart.getFullYear()} 年 ${periodStart.getMonth() + 1} 月` : `${periodStart.toLocaleDateString("zh-CN")} 至 ${new Date(periodEnd.getTime() - 1).toLocaleDateString("zh-CN")}`}</strong><button className="button-secondary" onClick={() => movePeriod(1)}>下一{periodMode === "month" ? "月" : "周"}</button></div>
      <div className="flex gap-2"><button className="button-secondary" onClick={() => download("csv")}>导出 CSV</button><button className="button-secondary" onClick={() => download("xlsx")}>导出 Excel</button></div>
    </div>
    {summary.data ? <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5"><div className="card"><p className="text-sm text-[var(--muted)]">{periodLabel}课时</p><p className="mt-2 text-2xl font-semibold">{(summary.data.completed_minutes / 60).toFixed(1)} 小时</p></div><div className="card"><p className="text-sm text-[var(--muted)]">{periodLabel}应收</p><p className="mt-2 text-2xl font-semibold">{money.format(summary.data.receivable_cents / 100)}</p></div><div className="card"><p className="text-sm text-[var(--muted)]">课程已分摊</p><p className="mt-2 text-2xl font-semibold">{money.format(summary.data.allocated_cents / 100)}</p></div><div className="card"><p className="text-sm text-[var(--muted)]">{periodLabel}实际到账</p><p className="mt-2 text-2xl font-semibold">{money.format(summary.data.received_cents / 100)}</p></div><div className="card"><p className="text-sm text-[var(--muted)]">尚未收取</p><p className="mt-2 text-2xl font-semibold text-amber-700">{money.format(summary.data.outstanding_cents / 100)}</p></div></section> : null}
    <div className="mt-6 grid gap-6 xl:grid-cols-[1.25fr_0.75fr]">
      <section className="space-y-3"><h2 className="text-xl font-semibold">课程账目</h2>{lessons.isPending ? <EmptyState>正在读取账目…</EmptyState> : lessons.data?.length ? lessons.data.map((item) => <article className="card" key={item.lesson_id}><div className="flex flex-wrap justify-between gap-3"><div><p className="text-sm text-[var(--muted)]">{dateTime.format(new Date(item.scheduled_start))} · {item.lesson_status}</p><h3 className="mt-1 font-semibold">{item.student_name} · {item.subject_name} · {item.theme}</h3><p className="mt-2 text-sm">{item.actual_minutes ?? item.planned_minutes} 分钟 · {money.format(item.unit_price_cents / 100)}/小时 {item.receivable_is_overridden ? "· 人工覆盖" : ""}</p></div><span className="badge">{statusLabels[item.payment_status]}</span></div><div className="mt-4 grid gap-3 text-sm sm:grid-cols-3"><div><span className="text-[var(--muted)]">应收</span><strong className="ml-2">{money.format(item.receivable_cents / 100)}</strong></div><div><span className="text-[var(--muted)]">已分摊</span><strong className="ml-2">{money.format(item.allocated_cents / 100)}</strong></div><div><span className="text-[var(--muted)]">未收</span><strong className="ml-2">{money.format(item.outstanding_cents / 100)}</strong></div></div><div className="mt-4 flex flex-wrap gap-2">{item.lesson_status !== "RESCHEDULED" ? <><button className="button-secondary" onClick={() => updatePricing(item)}>调整单价</button><button className="button-secondary" onClick={() => overrideReceivable(item)}>覆盖应收</button>{item.receivable_is_overridden ? <button className="button-secondary" onClick={() => resetReceivable(item)}>恢复自动计算</button> : null}</> : null}</div></article>) : <EmptyState>{periodLabel}暂无课程账目。</EmptyState>}</section>
      <form className="card h-fit space-y-3" onSubmit={createPayment}><h2 className="text-lg font-semibold">记录实际收款</h2><input className="field" type="datetime-local" value={paidAt} onChange={(event) => setPaidAt(event.target.value)} required /><select className="field" value={method} onChange={(event) => setMethod(event.target.value)}><option>微信</option><option>支付宝</option><option>银行转账</option><option>现金</option><option>其他</option></select><input className="field" type="text" inputMode="decimal" placeholder="实际到账金额（元）" value={amountYuan} onChange={(event) => setAmountYuan(event.target.value)} required /><input className="field" placeholder="交易单号/参考号（可选）" value={reference} onChange={(event) => setReference(event.target.value)} /><textarea className="field" placeholder="备注（可选）" value={notes} onChange={(event) => setNotes(event.target.value)} /><fieldset><legend className="label">分摊到欠费课程（可多选）</legend><div className="mt-2 max-h-64 space-y-2 overflow-y-auto">{outstanding.map((item) => <div className="grid grid-cols-[1fr_110px] items-center gap-2 rounded-lg border border-[var(--border)] p-3" key={item.lesson_id}><label className="text-sm"><input className="mr-2" type="checkbox" checked={item.lesson_id in allocations} onChange={(event) => toggleAllocation(item, event.target.checked)} />{item.student_name} · {item.theme}<span className="block pl-6 text-xs text-[var(--muted)]">未收 {money.format(item.outstanding_cents / 100)}</span></label>{item.lesson_id in allocations ? <input aria-label={`${item.theme}分摊金额`} className="field" inputMode="decimal" value={allocations[item.lesson_id]} onChange={(event) => setAllocations({...allocations, [item.lesson_id]: event.target.value})} /> : null}</div>)}</div></fieldset><button className="button-primary w-full" disabled={busy}>保存收款</button><p className="text-xs text-[var(--muted)]">允许先记录未完全分摊的到账款；分摊总额不能超过实际到账金额。</p></form>
    </div>
    <section className="mt-6 card"><h2 className="text-lg font-semibold">按学生汇总</h2>{summary.data?.students.length ? <div className="mt-4 overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr className="border-b"><th className="py-2">学生</th><th>课程</th><th>课时</th><th>应收</th><th>已分摊</th><th>未收</th></tr></thead><tbody>{summary.data.students.map((item) => <tr className="border-b last:border-0" key={item.student_id}><td className="py-3">{item.student_name}</td><td>{item.lesson_count}</td><td>{(item.completed_minutes / 60).toFixed(1)} 小时</td><td>{money.format(item.receivable_cents / 100)}</td><td>{money.format(item.allocated_cents / 100)}</td><td>{money.format(item.outstanding_cents / 100)}</td></tr>)}</tbody></table></div> : <p className="mt-3 text-sm text-[var(--muted)]">暂无汇总数据。</p>}</section>
    <section className="mt-6 space-y-3"><h2 className="text-xl font-semibold">实际收款记录</h2>{payments.data?.length ? payments.data.map((item) => <article className={`card ${item.voided_at ? "opacity-60" : ""}`} key={item.id}><div className="flex flex-wrap justify-between gap-3"><div><h3 className="font-semibold">{money.format(item.amount_cents / 100)} · {item.method}</h3><p className="mt-1 text-sm text-[var(--muted)]">{dateTime.format(new Date(item.paid_at))} · 已分摊 {money.format(item.allocated_cents / 100)} · 未分摊 {money.format(item.unallocated_cents / 100)}</p>{item.voided_at ? <p className="mt-2 text-sm text-red-700">已作废：{item.void_reason}</p> : null}</div>{!item.voided_at ? <div className="flex gap-2">{item.unallocated_cents > 0 ? <button className="button-secondary" onClick={() => addAllocation(item)}>追加分摊</button> : null}<button className="button-danger" onClick={() => voidPayment(item)}>作废</button></div> : null}</div></article>) : <EmptyState>{periodLabel}还没有收款记录。</EmptyState>}</section>
  </>;
}
