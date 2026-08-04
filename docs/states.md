# 关键业务状态

## 课程

`PLANNED → COMPLETED | CANCELED | RESCHEDULED`

- 调课不覆写原时间：原课程变为 `RESCHEDULED`，新建课程并关联原记录。
- 已完成课程不得直接取消；更正必须记录原因和审计。

## 计划和掌握度

- 计划条目：`NOT_STARTED → IN_PROGRESS → COMPLETED`；已学习状态可转入 `REVIEW_NEEDED`。
- 掌握度：`UNLEARNED / WEAK / DEVELOPING / PROFICIENT / MASTERED`。
- 掌握度更新必须产生 `MasteryEvidence`，不得仅存在于自然语言反馈。

## AI 任务

`QUEUED → RUNNING → SUCCEEDED | FAILED | CANCELED`

- Worker 领取时增加尝试次数并设置租约；长任务定期续租。
- 非终止失败按指数退避回到 `QUEUED`；达到上限进入 `FAILED`。
- 错误只保存稳定错误码和脱敏消息；重试不覆盖已有正式数据。

## 人工审核

`DRAFT → PENDING_REVIEW → APPROVED | REJECTED → SUPERSEDED`

- AI 结果只能成为新草稿版本。
- 批准反馈时，在同一数据库事务中发布反馈、更新计划、写入掌握度证据和下次课建议。
- 任何更新失败均回滚整个批准事务。

Phase 2 教案版本采用同一审核状态机：

- 生成、手工保存和局部重生成只创建 `DRAFT` 新版本。
- `DRAFT` 可提交为 `PENDING_REVIEW`；只有待审核版本可批准或驳回。
- 批准一个版本会把同一逻辑教案先前的批准版本标记为 `SUPERSEDED`，历史内容保持不可变。
- 只有 `APPROVED` 版本可导出 Word；AI 任务失败不会改变当前批准版本。

## 收款

付款状态由课程最终应收和已分摊金额实时计算：`UNPAID / PARTIAL / PAID / OVERPAID`。

- 课程完成后默认按实际分钟计算最终应收；此前展示计划应收。
- 人工覆盖应收必须填写理由并写审计。
- 取消课默认应收为零，但允许明确的取消费规则在 Phase 5 增加。
