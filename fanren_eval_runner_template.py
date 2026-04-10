import json
import re
import argparse
from collections import defaultdict

def normalize(s):
    if s is None:
        return ""
    if not isinstance(s, str):
        s = json.dumps(s, ensure_ascii=False)
    s = s.lower()
    s = re.sub(r"\s+", "", s)
    return s

def load_jsonl(path):
    data = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data

def contains_any(text, tokens):
    text_n = normalize(text)
    return any(normalize(t) in text_n for t in tokens)

def contains_all(text, tokens):
    text_n = normalize(text)
    return all(normalize(t) in text_n for t in tokens)

def planner_score(pred, exp):
    score = 0.0
    total = 0.0
    planner_pred = pred.get("planner", {})
    planner_exp = exp.get("planner", {})
    if not planner_exp:
        return 1.0

    if "task_type" in planner_exp:
        total += 1
        if planner_pred.get("task_type") == planner_exp["task_type"]:
            score += 1

    if "retrieval_needed" in planner_exp:
        total += 1
        if planner_pred.get("retrieval_needed") == planner_exp["retrieval_needed"]:
            score += 1

    if "retrieval_targets" in planner_exp:
        total += 1
        pred_targets = set(planner_pred.get("retrieval_targets", []))
        exp_targets = set(planner_exp.get("retrieval_targets", []))
        if pred_targets and len(pred_targets & exp_targets) / max(1, len(exp_targets)) >= 0.5:
            score += 1

    if "constraints" in planner_exp:
        total += 1
        pred_constraints = set(planner_pred.get("constraints", []))
        exp_constraints = set(planner_exp.get("constraints", []))
        if not exp_constraints:
            score += 1
        elif pred_constraints and len(pred_constraints & exp_constraints) / max(1, len(exp_constraints)) >= 0.4:
            score += 1

    return score / max(total, 1)

def answer_text(pred):
    if "answer" in pred:
        return pred["answer"]
    if "output" in pred:
        return pred["output"]
    return json.dumps(pred, ensure_ascii=False)

def score_presence(text, required):
    if not required:
        return 1.0
    hit = 0
    for item in required:
        if isinstance(item, list):
            if contains_any(text, item):
                hit += 1
        else:
            if contains_any(text, [item]):
                hit += 1
    return hit / len(required)

def score_absence(text, forbidden):
    if not forbidden:
        return 1.0
    bad = 0
    for item in forbidden:
        if contains_any(text, [item]):
            bad += 1
    return 1.0 - bad / len(forbidden)

def simple_length_ok(text, spec):
    if not spec:
        return 1.0
    n = len(text)
    if n < spec.get("min_chars", 0):
        return 0.0
    if n > spec.get("max_chars", 10**9):
        return 0.0
    return 1.0

def eval_case(case, pred):
    exp = case.get("expected_result", {})
    method = case.get("scoring", {}).get("method", "fact_check")
    threshold = case.get("scoring", {}).get("pass_threshold", 0.8)
    text = answer_text(pred)

    pscore = planner_score(pred, exp)

    required = []
    for key in ["gold_points", "required_points", "required_events", "required_behavior",
                "required_generation_points", "required_fields", "required_metrics", "required_views"]:
        required.extend(exp.get(key, []))

    forbidden = []
    for key in ["must_not_include", "forbidden_points", "forbidden_generation_points"]:
        forbidden.extend(exp.get(key, []))

    # additional field lists
    if "must_include" in exp:
        required.extend(exp["must_include"])
    if "must_include_any" in exp:
        required.extend(exp["must_include_any"])

    rscore = score_presence(text, required)
    fscore = score_absence(text, forbidden)
    lscore = simple_length_ok(text, exp.get("expected_length"))

    # method-specific composition
    if method == "schema_check":
        total = 0.5 * pscore + 0.5 * rscore
    elif method in {"policy_check", "uncertainty_check", "scope_guard", "safety_fact", "safety_consistency"}:
        total = 0.3 * pscore + 0.35 * rscore + 0.35 * fscore
    elif method in {"generative_checklist", "planner_plus_checklist"}:
        total = 0.25 * pscore + 0.45 * rscore + 0.20 * fscore + 0.10 * lscore
    elif method in {"planner_plus_fact", "fallback_fact", "multimodal_fact", "memory_plus_fact"}:
        total = 0.35 * pscore + 0.45 * rscore + 0.20 * fscore
    else:  # fact_check
        total = 0.25 * pscore + 0.55 * rscore + 0.20 * fscore

    return {
        "id": case["id"],
        "category": case["category"],
        "score": round(total, 4),
        "pass": total >= threshold,
        "threshold": threshold,
        "planner_score": round(pscore, 4),
        "required_score": round(rscore, 4),
        "forbidden_score": round(fscore, 4),
        "length_score": round(lscore, 4),
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--output", default="eval_report.json")
    args = parser.parse_args()

    cases = load_jsonl(args.cases)
    preds = {x["id"]: x for x in load_jsonl(args.predictions)}

    results = []
    by_cat = defaultdict(list)

    for case in cases:
        pred = preds.get(case["id"], {"id": case["id"], "answer": ""})
        res = eval_case(case, pred)
        results.append(res)
        by_cat[res["category"]].append(res["score"])

    overall = sum(r["score"] for r in results) / max(1, len(results))
    cat_scores = {k: round(sum(v)/len(v), 4) for k, v in by_cat.items()}

    report = {
        "overall_score": round(overall, 4),
        "category_scores": cat_scores,
        "pass_count": sum(1 for r in results if r["pass"]),
        "total_count": len(results),
        "results": results,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "overall_score": report["overall_score"],
        "pass_count": report["pass_count"],
        "total_count": report["total_count"],
        "category_scores": report["category_scores"]
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()