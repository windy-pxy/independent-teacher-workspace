from __future__ import annotations

from teacher_workspace.feedback_contract import LessonFeedbackContent
from teacher_workspace.lesson_plan_contract import LessonPlanContent

LESSON_PLAN_TEMPLATE_KEY = "lesson_plan.default"
LESSON_FEEDBACK_TEMPLATE_KEY = "lesson_feedback.default"

DEFAULT_LESSON_PLAN_SYSTEM_PROMPT = """你是一名严谨的一对一教师助理。
你必须根据教师提供的最小必要上下文生成可审核的结构化教案草稿。
不得虚构学生真实身份，不得把学生代号扩展为真实姓名。
题目、答案和解析必须一致；时间安排总和应等于课程计划时长。
输出必须严格符合给定 JSON Schema，不要添加 Schema 之外的字段。"""

DEFAULT_LESSON_PLAN_USER_PROMPT = """请为以下课程生成教师版教案草稿。

学生代号：{student_alias}
年级：{grade}
学科：{subject}
教材版本：{textbook_version}
当前基础：{current_foundation}
总目标：{overall_goal}
阶段目标：{stage_goal}
学习特点：{learning_characteristics}
教学注意事项：{attention_notes}
课程主题：{lesson_theme}
课程类型：{lesson_type}
计划时长：{planned_minutes} 分钟
课程特殊要求：{special_requirements}
长期计划及进度：{plan_context}
教师额外要求：{extra_requirements}

教案至少包含目标、逐段时间安排、知识讲解、典型例题、当堂练习、易错点、作业、答案解析和教师注意事项。
所有 Markdown 仅允许普通段落、加粗、斜体、有序/无序列表和简单表格，
不得包含 HTML、脚本或外部图片。"""


def lesson_plan_json_schema() -> dict[str, object]:
    return LessonPlanContent.model_json_schema()


DEFAULT_LESSON_FEEDBACK_SYSTEM_PROMPT = """你是一名严谨的一对一教师助理。
请把教师输入的简短课后关键词整理成结构化反馈草稿，并提出计划进度和知识点掌握度建议。
不得把建议当作正式记录；所有变更必须等待教师审核批准。
不得猜测学生真实身份，不得补充输入和课程上下文中不存在的具体事实。
计划条目只能使用上下文提供的 ID；知识点优先复用已有 ID，否则使用清晰、最小粒度的名称。
输出必须严格符合给定 JSON Schema，不要添加 Schema 之外的字段。"""

DEFAULT_LESSON_FEEDBACK_USER_PROMPT = """请将以下课后关键词整理为 JSON 结构化反馈草稿。

学生代号：{student_alias}
年级：{grade}
学科：{subject}
课程主题：{lesson_theme}
课程类型：{lesson_type}
计划时长：{planned_minutes} 分钟
实际时长：{actual_minutes} 分钟
关联教学计划条目：{plan_context}
已有知识点掌握度：{mastery_context}
教师关键词：{raw_feedback}
本次额外整理要求：{organize_instructions}

要求：
1. 忠实整理，不虚构课堂表现、错题或作业情况。
2. 对未提供的信息使用“未记录”，不要自行补全。
3. 计划进度建议只引用给出的 plan_item_id。
4. 掌握度建议必须给出简短证据说明。
5. 下次课建议应具体、可执行，并与薄弱点和未完成内容一致。"""


def lesson_feedback_json_schema() -> dict[str, object]:
    return LessonFeedbackContent.model_json_schema()
