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

    # 分析缺失的关键词
    missing_keywords = analyze_missing_keywords(text, required)

    return {
        "id": case["id"],
        "category": case["category"],
        "priority": case.get("priority", "P1"),
        "score": round(total, 4),
        "pass": total >= threshold,
        "threshold": threshold,
        "planner_score": round(pscore, 4),
        "required_score": round(rscore, 4),
        "forbidden_score": round(fscore, 4),
        "length_score": round(lscore, 4),
        "missing_keywords": missing_keywords,
    }


def analyze_missing_keywords(text, required):
    """分析缺失的关键词"""
    if not required:
        return []
    missing = []
    for item in required:
        if isinstance(item, list):
            # must_include_any 类型，只要有一个即可
            if not contains_any(text, item):
                missing.append(f"({', '.join(item[:3])}...)" if len(item) > 3 else f"({'/'.join(item)})")
        else:
            if not contains_any(text, [item]):
                missing.append(item)
    return missing[:5]  # 最多返回5个


def generate_detailed_report(cases, predictions):
    """生成详细报告，包含分层统计和失败分析"""
    from datetime import datetime

    results = []
    by_category = defaultdict(list)
    by_priority = defaultdict(list)
    case_map = {c["id"]: c for c in cases}

    for case in cases:
        pred = predictions.get(case["id"], {"id": case["id"], "answer": ""})
        res = eval_case(case, pred)
        results.append(res)
        by_category[res["category"]].append(res)
        by_priority[res["priority"]].append(res)

    # 计算统计
    overall_score = sum(r["score"] for r in results) / max(1, len(results))
    pass_count = sum(1 for r in results if r["pass"])

    # 按类别统计
    category_stats = {}
    for cat, items in by_category.items():
        scores = [i["score"] for i in items]
        passed = sum(1 for i in items if i["pass"])
        category_stats[cat] = {
            "score": round(sum(scores) / len(scores), 4),
            "pass_rate": round(passed / len(items), 4),
            "pass_count": passed,
            "count": len(items),
        }

    # 按优先级统计
    priority_stats = {}
    for pri, items in by_priority.items():
        scores = [i["score"] for i in items]
        passed = sum(1 for i in items if i["pass"])
        priority_stats[pri] = {
            "score": round(sum(scores) / len(scores), 4),
            "pass_rate": round(passed / len(items), 4),
            "pass_count": passed,
            "count": len(items),
        }

    # 失败案例分析（按 priority 排序，P0 优先）
    failures = []
    for r in sorted(results, key=lambda x: (0 if x["priority"] == "P0" else 1, -x["score"])):
        if not r["pass"]:
            case = case_map.get(r["id"], {})
            failures.append({
                "id": r["id"],
                "category": r["category"],
                "priority": r["priority"],
                "score": r["score"],
                "threshold": r["threshold"],
                "reason": format_failure_reason(r, case),
            })

    return {
        "meta": {
            "timestamp": datetime.now().isoformat(),
            "total_cases": len(cases),
        },
        "summary": {
            "overall_score": round(overall_score, 4),
            "pass_rate": round(pass_count / max(1, len(results)), 4),
            "pass_count": pass_count,
            "total_count": len(results),
        },
        "by_category": category_stats,
        "by_priority": priority_stats,
        "failures": failures,
        "details": results,
    }


def format_failure_reason(result, case):
    """格式化失败原因"""
    reasons = []
    if result["required_score"] < 0.8:
        missing = result.get("missing_keywords", [])
        if missing:
            reasons.append(f"缺少关键词: {', '.join(missing[:3])}")
        else:
            reasons.append("回答内容不完整")
    if result["planner_score"] < 0.8:
        reasons.append("planner 决策有误")
    if result["forbidden_score"] < 1.0:
        reasons.append("包含禁止内容")
    return "; ".join(reasons) if reasons else "得分未达阈值"


def print_summary(report, output_dir=None):
    """打印终端友好的摘要"""
    from datetime import datetime

    lines = []
    lines.append("=" * 60)
    lines.append(f"评测报告 - {report['meta']['timestamp'][:19]}")
    lines.append("=" * 60)

    # 总览
    s = report["summary"]
    lines.append("总览:")
    lines.append(f"  总分: {s['overall_score']:.4f}")
    lines.append(f"  通过率: {s['pass_rate']*100:.1f}% ({s['pass_count']}/{s['total_count']})")
    lines.append("")

    # 按任务类型
    lines.append("按任务类型:")
    for cat, stats in sorted(report["by_category"].items()):
        passed = stats["pass_count"]
        total = stats["count"]
        lines.append(f"  {cat:<20} {stats['score']:.3f}  {passed*100//max(1,total)}% passed ({passed}/{total})")
    lines.append("")

    # 按优先级
    lines.append("按优先级:")
    for pri in ["P0", "P1"]:
        if pri in report["by_priority"]:
            stats = report["by_priority"][pri]
            passed = stats["pass_count"]
            total = stats["count"]
            lines.append(f"  {pri:<20} {stats['score']:.3f}  {passed*100//max(1,total)}% passed ({passed}/{total})")
    lines.append("")

    # 失败案例
    failures = report.get("failures", [])
    if failures:
        lines.append(f"失败案例 (共 {len(failures)} 个, P0 优先):")
        for f in failures[:10]:  # 最多显示 10 个
            lines.append(f"  {f['id']} [{f['category']}] score={f['score']:.3f} < {f['threshold']}")
            lines.append(f"    → {f['reason']}")
        if len(failures) > 10:
            lines.append(f"  ... 还有 {len(failures) - 10} 个失败案例")
    lines.append("")

    # 输出文件
    if output_dir:
        lines.append("输出文件:")
        lines.append(f"  predictions: {output_dir}/predictions.jsonl")
        lines.append(f"  report:      {output_dir}/report.json")
        lines.append(f"  summary:     {output_dir}/report_summary.txt")
        lines.append(f"  html:        {output_dir}/report.html")
    lines.append("=" * 60)

    text = "\n".join(lines)
    print(text)
    return text


def generate_html_report(cases, predictions, report, output_path):
    """生成交互式 HTML 评测报告"""
    from datetime import datetime

    # 构建案例详情数据
    case_details = []
    case_map = {c["id"]: c for c in cases}

    for detail in report["details"]:
        case = case_map.get(detail["id"], {})
        pred = predictions.get(detail["id"], {"answer": ""})

        # 获取问题
        user_query = case.get("input", {}).get("user_query", "")
        # 获取预期答案
        gold_answer = case.get("expected_result", {}).get("gold_answer_short", "")
        # 获取系统答案
        system_answer = answer_text(pred)

        case_details.append({
            "id": detail["id"],
            "category": detail["category"],
            "priority": detail["priority"],
            "score": detail["score"],
            "threshold": detail["threshold"],
            "pass": detail["pass"],
            "user_query": user_query,
            "gold_answer": gold_answer,
            "system_answer": system_answer[:500] + ("..." if len(system_answer) > 500 else ""),
            "missing_keywords": detail.get("missing_keywords", []),
            "planner_score": detail["planner_score"],
            "required_score": detail["required_score"],
            "forbidden_score": detail["forbidden_score"],
        })

    # 分离失败和通过案例
    failures = [c for c in case_details if not c["pass"]]
    passes = [c for c in case_details if c["pass"]]

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>评测报告</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        .header {{ padding: 20px; border-bottom: 1px solid #eee; }}
        .header h1 {{ margin: 0 0 10px 0; font-size: 24px; }}
        .header .timestamp {{ color: #666; font-size: 14px; }}
        .summary {{ padding: 20px; display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; border-bottom: 1px solid #eee; }}
        .stat-card {{ background: #f8f9fa; padding: 15px; border-radius: 6px; }}
        .stat-card .label {{ font-size: 12px; color: #666; margin-bottom: 5px; }}
        .stat-card .value {{ font-size: 24px; font-weight: bold; }}
        .stat-card .value.good {{ color: #4caf50; }}
        .stat-card .value.bad {{ color: #f44336; }}
        .section {{ padding: 20px; border-bottom: 1px solid #eee; }}
        .section h2 {{ margin: 0 0 15px 0; font-size: 18px; display: flex; align-items: center; gap: 10px; }}
        .section h2 .count {{ font-size: 14px; color: #666; font-weight: normal; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #f8f9fa; font-weight: 600; }}
        .case-card {{ border: 1px solid #e0e0e0; margin: 10px 0; border-radius: 6px; overflow: hidden; }}
        .case-card.fail {{ border-left: 4px solid #f44336; }}
        .case-card.pass {{ border-left: 4px solid #4caf50; }}
        .case-header {{ padding: 12px 15px; cursor: pointer; background: #fafafa; display: flex; align-items: center; gap: 15px; }}
        .case-header:hover {{ background: #f0f0f0; }}
        .case-header .id {{ font-weight: 600; min-width: 100px; }}
        .case-header .category {{ background: #e3f2fd; padding: 2px 8px; border-radius: 4px; font-size: 12px; color: #1565c0; }}
        .case-header .score {{ margin-left: auto; font-family: monospace; }}
        .case-header .score.fail {{ color: #f44336; }}
        .case-header .score.pass {{ color: #4caf50; }}
        .case-header .arrow {{ transition: transform 0.2s; }}
        .case-card.expanded .case-header .arrow {{ transform: rotate(90deg); }}
        .case-detail {{ display: none; padding: 15px; background: white; }}
        .case-card.expanded .case-detail {{ display: block; }}
        .detail-row {{ margin: 10px 0; }}
        .detail-row .label {{ font-weight: 600; color: #666; font-size: 12px; margin-bottom: 5px; }}
        .detail-row .content {{ background: #f8f9fa; padding: 10px; border-radius: 4px; font-size: 14px; line-height: 1.6; }}
        .detail-row .content.missing {{ color: #f44336; }}
        .score-bar {{ display: flex; gap: 15px; margin-top: 10px; }}
        .score-item {{ flex: 1; }}
        .score-item .label {{ font-size: 11px; color: #666; }}
        .score-item .bar {{ height: 4px; background: #e0e0e0; border-radius: 2px; margin-top: 3px; }}
        .score-item .bar .fill {{ height: 100%; border-radius: 2px; }}
        .score-item .bar .fill.good {{ background: #4caf50; }}
        .score-item .bar .fill.bad {{ background: #f44336; }}
        .toggle-btn {{ background: #e3f2fd; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 14px; color: #1565c0; }}
        .toggle-btn:hover {{ background: #bbdefb; }}
        .collapsed .section-content {{ display: none; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>评测报告</h1>
            <div class="timestamp">{report['meta']['timestamp'][:19]}</div>
        </div>

        <div class="summary">
            <div class="stat-card">
                <div class="label">总分</div>
                <div class="value {'good' if report['summary']['overall_score'] >= 0.7 else 'bad'}">{report['summary']['overall_score']:.4f}</div>
            </div>
            <div class="stat-card">
                <div class="label">通过率</div>
                <div class="value {'good' if report['summary']['pass_rate'] >= 0.5 else 'bad'}">{report['summary']['pass_rate']*100:.1f}%</div>
            </div>
            <div class="stat-card">
                <div class="label">通过 / 总数</div>
                <div class="value">{report['summary']['pass_count']} / {report['summary']['total_count']}</div>
            </div>
        </div>

        <div class="section">
            <h2>按任务类型</h2>
            <table>
                <tr><th>类型</th><th>得分</th><th>通过率</th><th>通过/总数</th></tr>
                {_render_category_rows(report['by_category'])}
            </table>
        </div>

        <div class="section">
            <h2>按优先级</h2>
            <table>
                <tr><th>优先级</th><th>得分</th><th>通过率</th><th>通过/总数</th></tr>
                {_render_priority_rows(report['by_priority'])}
            </table>
        </div>

        <div class="section">
            <h2>失败案例 <span class="count">({len(failures)} 个)</span></h2>
            {_render_case_cards(failures, expanded=True)}
        </div>

        <div class="section collapsed" id="passed-section">
            <h2>
                <button class="toggle-btn" onclick="togglePassed()">展开</button>
                通过案例 <span class="count">({len(passes)} 个)</span>
            </h2>
            <div class="section-content">
                {_render_case_cards(passes, expanded=False)}
            </div>
        </div>
    </div>

    <script>
        function toggleCase(card) {{
            card.classList.toggle('expanded');
        }}

        function togglePassed() {{
            const section = document.getElementById('passed-section');
            const btn = section.querySelector('.toggle-btn');
            section.classList.toggle('collapsed');
            btn.textContent = section.classList.contains('collapsed') ? '展开' : '折叠';
        }}

        // 默认展开前 3 个失败案例
        document.querySelectorAll('.case-card.fail').forEach((card, i) => {{
            if (i < 3) card.classList.add('expanded');
        }});
    </script>
</body>
</html>'''

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


def _render_category_rows(by_category):
    rows = []
    for cat, stats in sorted(by_category.items()):
        rate = f"{stats['pass_rate']*100:.0f}%"
        rows.append(f"<tr><td>{cat}</td><td>{stats['score']:.4f}</td><td>{rate}</td><td>{stats['pass_count']}/{stats['count']}</td></tr>")
    return "\n".join(rows)


def _render_priority_rows(by_priority):
    rows = []
    for pri in ["P0", "P1"]:
        if pri in by_priority:
            stats = by_priority[pri]
            rate = f"{stats['pass_rate']*100:.0f}%"
            rows.append(f"<tr><td>{pri}</td><td>{stats['score']:.4f}</td><td>{rate}</td><td>{stats['pass_count']}/{stats['count']}</td></tr>")
    return "\n".join(rows)


def _render_case_cards(cases, expanded=False):
    cards = []
    for c in cases:
        status = "pass" if c["pass"] else "fail"
        query_short = c["user_query"][:60] + ("..." if len(c["user_query"]) > 60 else "")

        # 分数条
        score_bars = f'''
        <div class="score-bar">
            <div class="score-item">
                <div class="label">Planner: {c['planner_score']:.2f}</div>
                <div class="bar"><div class="fill {'good' if c['planner_score'] >= 0.8 else 'bad'}" style="width:{c['planner_score']*100}%"></div></div>
            </div>
            <div class="score-item">
                <div class="label">Required: {c['required_score']:.2f}</div>
                <div class="bar"><div class="fill {'good' if c['required_score'] >= 0.8 else 'bad'}" style="width:{c['required_score']*100}%"></div></div>
            </div>
            <div class="score-item">
                <div class="label">Forbidden: {c['forbidden_score']:.2f}</div>
                <div class="bar"><div class="fill {'good' if c['forbidden_score'] >= 0.9 else 'bad'}" style="width:{c['forbidden_score']*100}%"></div></div>
            </div>
        </div>'''

        # 缺失关键词
        missing_html = ""
        if c["missing_keywords"]:
            missing_html = f'''
            <div class="detail-row">
                <div class="label">缺失关键词</div>
                <div class="content missing">{", ".join(c['missing_keywords'])}</div>
            </div>'''

        card = f'''
        <div class="case-card {status}" onclick="toggleCase(this)">
            <div class="case-header">
                <span class="id">{c['id']}</span>
                <span class="category">{c['category']}</span>
                <span>{query_short}</span>
                <span class="score {status}">{c['score']:.3f} / {c['threshold']}</span>
                <span class="arrow">▶</span>
            </div>
            <div class="case-detail">
                <div class="detail-row">
                    <div class="label">问题</div>
                    <div class="content">{c['user_query']}</div>
                </div>
                <div class="detail-row">
                    <div class="label">系统答案</div>
                    <div class="content">{c['system_answer']}</div>
                </div>
                <div class="detail-row">
                    <div class="label">预期答案</div>
                    <div class="content">{c['gold_answer']}</div>
                </div>
                {missing_html}
                {score_bars}
            </div>
        </div>'''
        cards.append(card)
    return "\n".join(cards)

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