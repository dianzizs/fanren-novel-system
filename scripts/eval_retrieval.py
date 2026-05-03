#!/usr/bin/env python
"""检索评测脚本。

运行方式：
    conda run -n chaishu python -m scripts.eval_retrieval

指标：
    - Recall@K: 前K个结果中相关文档的比例
    - MRR@K: 平均倒数排名
    - nDCG@K: 归一化折损累积增益

输出：
    data/eval/retrieval_report.json
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# 添加项目根目录到 path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """计算 Recall@K。

    Recall@K = |relevant ∩ retrieved[:k]| / |relevant|

    Args:
        retrieved_ids: 检索返回的文档ID列表（按得分排序）
        relevant_ids: 相关文档ID集合
        k: 截断位置

    Returns:
        Recall@K 分数 [0, 1]
    """
    if not relevant_ids:
        return 0.0

    retrieved_set = set(retrieved_ids[:k])
    hits = len(retrieved_set & relevant_ids)
    return hits / len(relevant_ids)


def mrr_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """计算 MRR@K (Mean Reciprocal Rank)。

    MRR@K = 1/rank of first relevant doc (within top K)

    Args:
        retrieved_ids: 检索返回的文档ID列表（按得分排序）
        relevant_ids: 相关文档ID集合
        k: 截断位置

    Returns:
        MRR@K 分数 [0, 1]
    """
    if not relevant_ids:
        return 0.0

    for i, doc_id in enumerate(retrieved_ids[:k]):
        if doc_id in relevant_ids:
            return 1.0 / (i + 1)
    return 0.0


def dcg_at_k(relevances: list[int], k: int) -> float:
    """计算 DCG@K (Discounted Cumulative Gain)。

    DCG@K = sum(rel_i / log2(i + 1)) for i in 1..K

    Args:
        relevances: 相关性得分列表（按排名顺序）
        k: 截断位置

    Returns:
        DCG@K 分数
    """
    dcg = 0.0
    for i, rel in enumerate(relevances[:k]):
        if i == 0:
            dcg += rel
        else:
            dcg += rel / math.log2(i + 2)
    return dcg


def ndcg_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """计算 nDCG@K (Normalized Discounted Cumulative Gain)。

    nDCG@K = DCG@K / IDCG@K

    IDCG 是理想情况下（所有相关文档排在最前面）的 DCG。

    Args:
        retrieved_ids: 检索返回的文档ID列表（按得分排序）
        relevant_ids: 相关文档ID集合
        k: 截断位置

    Returns:
        nDCG@K 分数 [0, 1]
    """
    if not relevant_ids:
        return 0.0

    # 计算实际 DCG：相关文档为1，不相关为0
    relevances = [1 if doc_id in relevant_ids else 0 for doc_id in retrieved_ids[:k]]
    dcg = dcg_at_k(relevances, k)

    # 计算理想 DCG：所有相关文档排在最前面
    ideal_relevances = [1] * min(len(relevant_ids), k)
    idcg = dcg_at_k(ideal_relevances, k)

    if idcg == 0:
        return 0.0

    return dcg / idcg


def load_jsonl(path: str) -> list[dict[str, Any]]:
    """加载 JSONL 文件。"""
    data = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def run_retrieval_evaluation(
    cases: list[dict[str, Any]],
    retrieve_fn,
    k_values: list[int] = None,
) -> dict[str, Any]:
    """运行检索评测。

    Args:
        cases: 评测案例列表，每个案例包含：
            - id: 案例ID
            - query: 查询文本
            - relevant_doc_ids: 相关文档ID列表
        retrieve_fn: 检索函数，接收 (query, top_k) 参数
        k_values: 要计算的 K 值列表

    Returns:
        评测结果字典
    """
    if k_values is None:
        k_values = [5, 10, 20]

    results = []

    for case in cases:
        case_id = case["id"]
        query = case["query"]
        relevant_doc_ids = set(case.get("relevant_doc_ids", []))

        if not relevant_doc_ids:
            print(f"警告: 案例 {case_id} 没有标注相关文档，跳过")
            continue

        # 调用检索函数，获取足够多的结果
        max_k = max(k_values)
        retrieved = retrieve_fn(query, top_k=max_k)
        retrieved_ids = [r["id"] for r in retrieved]

        # 计算各指标
        case_result = {
            "id": case_id,
            "query": query,
            "num_relevant": len(relevant_doc_ids),
            "num_retrieved": len(retrieved_ids),
        }

        for k in k_values:
            case_result[f"recall@{k}"] = recall_at_k(retrieved_ids, relevant_doc_ids, k)
            case_result[f"mrr@{k}"] = mrr_at_k(retrieved_ids, relevant_doc_ids, k)
            case_result[f"ndcg@{k}"] = ndcg_at_k(retrieved_ids, relevant_doc_ids, k)

        results.append(case_result)

    # 计算汇总统计
    if not results:
        return {"error": "没有有效的评测结果"}

    summary = {
        "total_cases": len(results),
        "k_values": k_values,
    }

    for k in k_values:
        recall_key = f"recall@{k}"
        mrr_key = f"mrr@{k}"
        ndcg_key = f"ndcg@{k}"

        summary[f"mean_recall@{k}"] = sum(r[recall_key] for r in results) / len(results)
        summary[f"mean_mrr@{k}"] = sum(r[mrr_key] for r in results) / len(results)
        summary[f"mean_ndcg@{k}"] = sum(r[ndcg_key] for r in results) / len(results)

    return {
        "meta": {
            "timestamp": datetime.now().isoformat(),
            "total_cases": len(results),
        },
        "summary": summary,
        "details": results,
    }


def print_retrieval_report(report: dict[str, Any]) -> str:
    """打印检索评测报告。"""
    lines = []
    lines.append("=" * 60)
    lines.append(f"检索评测报告 - {report['meta']['timestamp'][:19]}")
    lines.append("=" * 60)

    summary = report["summary"]
    k_values = summary["k_values"]

    lines.append(f"总案例数: {summary['total_cases']}")
    lines.append("")

    for k in k_values:
        lines.append(f"K={k}:")
        lines.append(f"  Recall@{k}:  {summary[f'mean_recall@{k}']:.4f}")
        lines.append(f"  MRR@{k}:     {summary[f'mean_mrr@{k}']:.4f}")
        lines.append(f"  nDCG@{k}:    {summary[f'mean_ndcg@{k}']:.4f}")
        lines.append("")

    # 打印最差案例
    details = report.get("details", [])
    if details:
        worst_recall = sorted(details, key=lambda x: x.get("recall@10", 0))[:5]
        lines.append("最差案例 (by Recall@10):")
        for r in worst_recall:
            lines.append(f"  {r['id']}: Recall@10={r.get('recall@10', 0):.3f}")
        lines.append("")

    lines.append("=" * 60)

    text = "\n".join(lines)
    print(text)
    return text


def create_retrieval_function():
    """创建检索函数。"""
    from novel_system.service import create_service

    service = create_service()
    service.ensure_indexed("凡人修仙传")

    def retrieve(query: str, top_k: int = 20) -> list[dict]:
        """执行检索并返回文档列表。"""
        from novel_system.models import AskRequest, Scope

        request = AskRequest(
            user_query=query,
            scope=Scope(chapters=list(range(1, 15))),
            debug=False,
        )
        response = service.ask("凡人修仙传", request)

        # 返回证据文档
        return [
            {"id": e.quote[:50], "chapter": e.chapter, "quote": e.quote, "score": e.score}
            for e in response.evidence[:top_k]
        ]

    return retrieve


def main():
    """主函数。"""
    print("=" * 60)
    print(f"检索评测开始 - {datetime.now().isoformat()[:19]}")
    print("=" * 60)

    # 加载评测数据
    eval_path = ROOT / "data" / "eval" / "fanren_retrieval_eval_v1.jsonl"
    if not eval_path.exists():
        print(f"错误：找不到评测数据文件 {eval_path}")
        print("请先创建评测数据文件，格式如下：")
        print('{"id": "case_001", "query": "韩立为什么参加七玄门测试", "relevant_doc_ids": ["ch1-chunk0", "ch1-chunk1"]}')
        sys.exit(1)

    cases = load_jsonl(str(eval_path))
    print(f"加载评测案例: {len(cases)} 个")

    # 创建检索函数
    print("初始化检索服务...")
    retrieve_fn = create_retrieval_function()

    # 运行评测
    print("运行检索评测...")
    report = run_retrieval_evaluation(
        cases,
        retrieve_fn,
        k_values=[5, 10, 20],
    )

    # 保存报告
    output_dir = ROOT / "data" / "eval"
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = output_dir / "retrieval_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n报告已保存: {report_path}")

    # 打印报告
    print_retrieval_report(report)

    print("\n" + "=" * 60)
    print("检索评测完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
