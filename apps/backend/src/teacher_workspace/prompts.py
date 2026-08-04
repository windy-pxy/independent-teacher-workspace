from __future__ import annotations

from teacher_workspace.lesson_plan_contract import LessonPlanContent

LESSON_PLAN_TEMPLATE_KEY = "lesson_plan.default"

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
