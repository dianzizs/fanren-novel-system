#!/usr/bin/env python
"""完整评测运行脚本。

运行方式：
    conda run -n chaishu python -m scripts.run_full_eval

输出：
    data/eval_full/report.json
    data/eval_full/report.html
    data/eval_full/report_summary.txt
    data/eval_full/predictions.jsonl
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# 添加项目根目录到 path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from novel_system.service import create_service
from novel_system.models import AskRequest, ContinueRequest, Scope, ConversationTurn

# 导入评测模板中的函数
from eval_runner_template import (
    load_jsonl,
    generate_detailed_report,
    print_summary,
    generate_html_report,
)


def run_prediction(case: dict, service) -> dict[str, Any]:
    """运行单个评测案例，返回预测结果。"""
    input_data = case.get("input", {})
    book_id = input_data.get("book", "凡人修仙传")

    # 构建请求
    user_query = input_data.get("user_query", "")
    scope_data = input_data.get("scope", {})
    chapters = scope_data.get("chapters", [])
    conversation_history = [
        ConversationTurn(**turn)
        for turn in input_data.get("conversation_history", [])
    ]

    # 根据任务类型选择 API
    task_type = case.get("expected_result", {}).get("planner", {}).get("task_type", "qa")

    if task_type == "continuation":
        request = ContinueRequest(
            user_query=user_query,
            scope=Scope(chapters=chapters),
            conversation_history=conversation_history,
            debug=True,
        )
        response = service.continue_story(book_id, request)
    else:
        request = AskRequest(
            user_query=user_query,
            scope=Scope(chapters=chapters),
            conversation_history=conversation_history,
            retrieved_text=input_data.get("retrieved_text"),
            test_harness=input_data.get("test_harness", {}),
            debug=True,
        )
        response = service.ask(book_id, request)

    # 构建预测结果
    result = {
        "id": case["id"],
        "planner": {
            "task_type": response.planner.task_type,
            "retrieval_needed": response.planner.retrieval_needed,
            "retrieval_targets": response.planner.retrieval_targets,
            "constraints": response.planner.constraints,
        },
        "answer": response.answer,
        "evidence": [
            {
                "chapter": e.chapter,
                "quote": e.quote,
                "score": e.score,
            }
            for e in response.evidence
        ],
        "uncertainty": response.confidence,
    }

    return result


def main():
    """运行完整评测。"""
    print("=" * 60)
    print(f"评测开始 - {datetime.now().isoformat()[:19]}")
    print("=" * 60)

    # 加载评测案例
    cases_path = ROOT / "fanren_eval_cases_v1.jsonl"
    if not cases_path.exists():
        print(f"错误：找不到评测案例文件 {cases_path}")
        sys.exit(1)

    cases = load_jsonl(str(cases_path))
    print(f"加载评测案例: {len(cases)} 个")

    # 创建输出目录
    output_dir = ROOT / "data" / "eval_full"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 创建服务实例
    print("初始化服务...")
    service = create_service()

    # 确保书籍已索引
    book_id = "凡人修仙传"
    print(f"检查书籍索引状态: {book_id}...")
    try:
        service.ensure_indexed(book_id)
        print(f"书籍 {book_id} 已就绪")
    except FileNotFoundError:
        print(f"书籍 {book_id} 未索引，正在建立索引...")
        service.index_book(book_id, "凡人修仙传")
        print(f"索引完成")

    # 运行预测
    predictions = {}
    for i, case in enumerate(cases):
        case_id = case["id"]
        print(f"[{i+1}/{len(cases)}] 运行 {case_id}...", end=" ", flush=True)
        try:
            pred = run_prediction(case, service)
            predictions[case_id] = pred
            print("[OK]")
        except Exception as e:
            print(f"[FAIL] 错误: {e}")
            predictions[case_id] = {
                "id": case_id,
                "answer": "",
                "error": str(e),
            }

    # 保存预测结果
    preds_path = output_dir / "predictions.jsonl"
    with open(preds_path, "w", encoding="utf-8") as f:
        for case in cases:
            pred = predictions.get(case["id"], {"id": case["id"], "answer": ""})
            f.write(json.dumps(pred, ensure_ascii=False) + "\n")
    print(f"\n预测结果已保存: {preds_path}")

    # 生成报告
    print("\n生成评测报告...")
    report = generate_detailed_report(cases, predictions)

    # 保存 JSON 报告
    report_path = output_dir / "report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"JSON 报告已保存: {report_path}")

    # 生成 HTML 报告
    html_path = output_dir / "report.html"
    generate_html_report(cases, predictions, report, str(html_path))
    print(f"HTML 报告已保存: {html_path}")

    # 保存摘要
    summary_text = print_summary(report, str(output_dir))
    summary_path = output_dir / "report_summary.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary_text)
    print(f"摘要已保存: {summary_path}")

    print("\n" + "=" * 60)
    print("评测完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
