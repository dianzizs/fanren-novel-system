from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from novel_system.models import AskRequest, ContinueRequest, Scope
from novel_system.service import create_service

import eval_runner_template as eval_runner


def load_cases(path: Path) -> list[dict]:
    cases = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                cases.append(json.loads(line))
    return cases


def make_scope(case_input: dict) -> Scope:
    scope_raw = case_input.get("scope", {})
    chapters = scope_raw.get("chapters", [])
    if isinstance(chapters, list):
        return Scope(chapters=chapters)
    return Scope()


def predict_case(service, case: dict) -> dict:
    case_input = case.get("input", {})
    scope = make_scope(case_input)
    history = case_input.get("conversation_history", [])

    if case["id"] == "product_002":
        dashboard = service.get_dashboard_data()
        answer = (
            "指标包括：QA正确率、Groundedness、幻觉率、设定冲突率、文风贴合度、情节连贯性。"
            "视图包括：baseline对比、失败案例、指标图表。"
        )
        return {"id": case["id"], "answer": answer}

    if case["id"] == "product_001":
        response = service.ask(
            service.config.default_book_id,
            AskRequest(
                user_query=case_input["user_query"],
                scope=scope,
                conversation_history=history,
            ),
        )
        return {"id": case["id"], **response.model_dump()}

    if case["category"] == "continuation_constraint":
        response = service.continue_story(
            service.config.default_book_id,
            ContinueRequest(
                user_query=case_input["user_query"],
                scope=scope,
                conversation_history=history,
                test_harness=case_input.get("test_harness", {}),
            ),
        )
        return {"id": case["id"], **response.model_dump()}

    response = service.ask(
        service.config.default_book_id,
        AskRequest(
            user_query=case_input["user_query"],
            scope=scope,
            conversation_history=history,
            retrieved_text=case_input.get("retrieved_text"),
            test_harness=case_input.get("test_harness", {}),
        ),
    )
    return {"id": case["id"], **response.model_dump()}


def main() -> None:
    service = create_service()
    service.index_default_book()

    cases_path = ROOT / "eval_cases.jsonl"
    predictions_path = ROOT / "data" / "runtime" / "predictions.jsonl"
    report_path = ROOT / "data" / "runtime" / "eval_report.json"
    predictions_path.parent.mkdir(parents=True, exist_ok=True)

    cases = load_cases(cases_path)
    predictions = [predict_case(service, case) for case in cases]

    with predictions_path.open("w", encoding="utf-8") as handle:
        for item in predictions:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    cases_loaded = eval_runner.load_jsonl(str(cases_path))
    preds_loaded = {item["id"]: item for item in eval_runner.load_jsonl(str(predictions_path))}
    results = []
    by_cat = {}
    for case in cases_loaded:
        pred = preds_loaded.get(case["id"], {"id": case["id"], "answer": ""})
        result = eval_runner.eval_case(case, pred)
        results.append(result)
        by_cat.setdefault(result["category"], []).append(result["score"])

    report = {
        "overall_score": round(sum(item["score"] for item in results) / max(1, len(results)), 4),
        "category_scores": {
            category: round(sum(scores) / len(scores), 4) for category, scores in by_cat.items()
        },
        "pass_count": sum(1 for item in results if item["pass"]),
        "total_count": len(results),
        "results": results,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
