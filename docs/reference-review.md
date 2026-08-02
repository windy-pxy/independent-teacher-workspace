# 开源参考审查

检查日期：2026-08-02。Phase 0 采用 clean-room 实现，只借鉴公开产品思想；没有复制这些项目的代码、素材或提示词正文。

| 项目 | 许可证 | 可借鉴内容 | 使用边界 |
|---|---|---|---|
| [Claw-ED](https://github.com/SirhanMacx/Claw-ED) | MIT | 本地优先、提供商抽象、质量门、集中审批 | 若未来直接复用代码，保留版权和 MIT 文本；当前仅借鉴思想。 |
| [QuizWeaver](https://github.com/Robyn-Collie/QuizWeaver) | MIT | 模型生成草稿、确定性规则校验、教师决定、隐私与成本透明 | 不复制实现；按本项目单教师闭环重新设计。 |
| [teacher-planner-obsidian](https://github.com/NSDerred/teacher-planner-obsidian) | GPL-3.0 | 日历、模板、课程准备状态和本地数据体验 | 不复制代码，避免把 GPL 衍生义务引入本项目。 |
| [Tuition-Management-System](https://github.com/AzimKrishna/Tuition-Management-System) | 未在仓库根目录发现许可证 | 仪表盘、排课、账单与报表的业务分区 | 按默认版权保护处理，不复制代码、SQL、图片或页面。 |
| [education-ai-skills](https://github.com/KRASA-AI/education-ai-skills) | MIT | 提示词按用途集中、结构化、版本化 | 当前仅借鉴组织方式；直接复用时履行 MIT 署名。 |
| [k12-teacher-skills](https://github.com/anthropics/k12-teacher-skills) | Apache-2.0 | 教案规划方法、评估框架和人工审核 | 直接复用时保留许可证、变更声明和适用 NOTICE。 |

任何后续阶段若要引入第三方代码或提示词，必须先记录具体文件、提交版本、许可证、修改内容和归属声明，再进行实现。
