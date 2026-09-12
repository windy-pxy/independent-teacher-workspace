"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";

export default function PrivacyPage() {
  const [supportContact, setSupportContact] = useState<string>();
  useEffect(() => {
    api<{ support_contact?: string }>("/auth/registration")
      .then((value) => setSupportContact(value.support_contact))
      .catch(() => undefined);
  }, []);
  return (
    <main className="mx-auto max-w-3xl px-5 py-12">
      <article className="card space-y-6 p-8">
        <div>
          <p className="page-kicker">PRIVACY NOTICE · 2026-09-11</p>
          <h1 className="page-title">隐私说明</h1>
          <p className="page-description">面向独立教师工作台账户及其录入的教学资料。</p>
        </div>
        <section><h2 className="text-xl font-semibold">收集与用途</h2><p className="mt-2 leading-7">系统保存账户名、密码哈希、登录会话，以及教师主动录入的学生代号、课程、教案、反馈、错题、资料与收费记录，用于提供工作台功能。请尽量使用学生代号，不录入完成教学目的所不需要的身份信息。</p></section>
        <section><h2 className="text-xl font-semibold">AI 处理</h2><p className="mt-2 leading-7">只有教师主动生成时，系统才把完成任务所需的最少片段发送给已配置的模型提供商。API 密钥不会发送给其他教师。AI 内容始终先作为草稿，教师审核后才可更新正式记录。</p></section>
        <section><h2 className="text-xl font-semibold">存储、隔离与保留</h2><p className="mt-2 leading-7">每位教师的数据以服务端账户边界隔离并持久化在 PostgreSQL 与私有文件存储中。退出登录不会删除资料。教师申请删除后有 7 天撤销期；到期后账户及在线业务资料会被清除。加密备份可能按备份轮换周期延迟清除，期间不会用于正常业务。</p></section>
        <section><h2 className="text-xl font-semibold">教师责任与权利</h2><p className="mt-2 leading-7">教师应确保有权处理录入的学生资料，不上传无关敏感信息。教师可导出自己的资料、修改密码、撤销会话并申请删除账户；这些功能在公网开放前完成最终验收。</p></section>
        <p className="text-sm text-[var(--muted)]">当前版本：2026-09-11。{supportContact ? `隐私与账户问题联系：${supportContact}` : "当前是本地/封闭测试环境；尚未配置公网运营者联系方式，不能开放公共注册。"}</p>
        <Link className="button-secondary" href="/register">返回注册</Link>
      </article>
    </main>
  );
}
