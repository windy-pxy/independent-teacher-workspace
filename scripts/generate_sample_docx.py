from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path

from teacher_workspace.docx_generator import (
    LessonDocumentMetadata,
    build_lesson_plan_docx,
)
from teacher_workspace.lesson_plan_contract import LessonPlanContent


async def build_sample() -> bytes:
    content = LessonPlanContent.model_validate(
        {
            "objectives": ["理解速度的含义和单位", "能使用速度公式解决基础问题"],
            "schedule": [
                {"minutes": 10, "title": "复习诊断", "activities_markdown": "复习长度、时间和单位换算。"},
                {"minutes": 25, "title": "概念讲解", "activities_markdown": "通过生活情境建立**速度**概念。"},
                {"minutes": 30, "title": "例题练习", "activities_markdown": "示范公式使用，再完成同类变式。"},
                {"minutes": 15, "title": "纠错提升", "activities_markdown": "分析单位混用和漏写单位问题。"},
                {"minutes": 10, "title": "总结作业", "activities_markdown": "学生复述步骤并完成出口题。"},
            ],
            "knowledge_explanations": [
                {"id": "speed", "title": "速度的定义", "body_markdown": "速度表示物体运动的快慢，计算式为 **速度 = 路程 / 时间**。"},
                {"id": "unit", "title": "单位换算", "body_markdown": "计算前先统一路程和时间单位，结果必须写单位。"},
            ],
            "examples": [
                {"id": "example-1", "stem_markdown": "一辆自行车 2 小时行驶 30 千米，平均速度是多少？", "answer_markdown": "15 千米/时。", "analysis_markdown": "使用 30 / 2 = 15，并写出速度单位。", "difficulty": "BASIC"}
            ],
            "in_class_exercises": [
                {"id": "practice-1", "stem_markdown": "小车 5 秒行驶 20 米，速度是多少？", "answer_markdown": "4 米/秒。", "analysis_markdown": "20 / 5 = 4，单位为米/秒。", "difficulty": "MEDIUM"}
            ],
            "common_mistakes": ["路程与时间单位不匹配", "只写数值没有写单位"],
            "homework": [
                {"id": "homework-1", "stem_markdown": "跑步者 3 分钟跑 600 米，求平均速度。", "answer_markdown": "200 米/分。", "analysis_markdown": "600 / 3 = 200；若换算米/秒，应先把 3 分钟换成 180 秒。", "difficulty": "MEDIUM"}
            ],
            "teacher_notes": ["示例学生和题目均为虚构内容。", "先检查单位，再代入公式。"],
        }
    )
    metadata = LessonDocumentMetadata(
        student_alias="示例学生丙",
        grade="八年级",
        subject="物理",
        theme="速度与路程",
        scheduled_start=datetime(2026, 8, 10, 10, 0, tzinfo=UTC),
        planned_minutes=90,
    )
    return build_lesson_plan_docx(metadata, content)


def main() -> None:
    parser = argparse.ArgumentParser(description="生成虚构的 Phase 2 教师版教案示例")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("var/exports/2026-08-10_示例学生丙_物理_速度与路程.docx"),
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(asyncio.run(build_sample()))
    print(args.output.resolve())


if __name__ == "__main__":
    main()
