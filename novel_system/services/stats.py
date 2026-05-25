from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..models import (
    ConversationTurn,
    EvaluationDashboardData,
    EvaluationMetric,
)

ARTIFACT_LABELS = {
    "manifest": "书目状态",
    "chapters": "分章结果",
    "scene_segments": "场景片段",
    "character_registry": "角色注册表",
    "chapter_chunks": "切片结果（已废弃）",
    "chapter_summaries": "章节摘要（已废弃）",
    "event_timeline": "事件时间线（已废弃）",
    "character_card": "人物卡（已废弃）",
    "relationship_graph": "关系图（已废弃）",
    "world_rule": "世界规则（已废弃）",
    "canon_memory": "设定记忆（已废弃）",
    "recent_plot": "近期剧情（已废弃）",
    "style_samples": "风格样本（已废弃）",
    "vision_parse": "视觉解析（已废弃）",
}


class StatsServiceMixin:
    """Mixin for stats extraction and artifacts dashboard metadata."""

    def get_storage_stats(self) -> dict[str, Any]:
        """获取存储统计信息"""
        stats = {
            "books": [],
            "total_index_size": 0,
            "total_uploads_size": 0,
        }
        for manifest in self.repo.list_books():
            book_id = manifest["id"]
            index_path = self.config.data_dir / "books" / book_id
            index_size = sum(f.stat().st_size for f in index_path.rglob("*") if f.is_file()) if index_path.exists() else 0
            stats["books"].append({
                "id": book_id,
                "title": manifest["title"],
                "index_size": index_size,
                "source": manifest.get("source", "local"),
            })
            stats["total_index_size"] += index_size

        uploads_path = self.config.data_dir / "uploads"
        if uploads_path.exists():
            stats["total_uploads_size"] = sum(f.stat().st_size for f in uploads_path.rglob("*") if f.is_file())
        return stats

    def _record_token_usage(self, book_id: str, usage: dict[str, int]) -> None:
        """记录 LLM token 使用量并持久化到磁盘 (线程安全)"""
        if not usage:
            return
        with self._lock:
            self.token_usage[book_id]["prompt_tokens"] += usage.get("prompt_tokens", 0)
            self.token_usage[book_id]["completion_tokens"] += usage.get("completion_tokens", 0)
            self.token_usage[book_id]["total_tokens"] += usage.get("total_tokens", 0)

            # Save to disk
            book_dir = self.config.data_dir / "books" / book_id
            book_dir.mkdir(parents=True, exist_ok=True)
            token_file = book_dir / "token_usage.json"
            try:
                with open(token_file, "w", encoding="utf-8") as f:
                    json.dump(self.token_usage[book_id], f, ensure_ascii=False, indent=2)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to save token usage to {token_file}: {e}")

    def get_token_stats(self) -> dict[str, Any]:
        """获取 token 统计信息"""
        books_map = {m["id"]: m["title"] for m in self.repo.list_books()}
        books = []
        total_prompt = 0
        total_completion = 0
        total_tokens = 0
        with self._lock:
            token_usage_copy = dict(self.token_usage)
        for book_id, usage in token_usage_copy.items():
            books.append({
                "book_id": book_id,
                "title": books_map.get(book_id, book_id),
                "prompt_tokens": usage["prompt_tokens"],
                "completion_tokens": usage["completion_tokens"],
                "total_tokens": usage["total_tokens"],
            })
            total_prompt += usage["prompt_tokens"]
            total_completion += usage["completion_tokens"]
            total_tokens += usage["total_tokens"]
        return {
            "books": books,
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_tokens,
        }

    def get_book_artifact_catalog(self, book_id: str) -> dict[str, Any]:
        manifest = next((book for book in self.repo.list_books() if book["id"] == book_id), None)
        if not manifest:
            raise FileNotFoundError(f"Book {book_id} not found")

        artifacts = []
        for name, label in ARTIFACT_LABELS.items():
            try:
                content = self.repo.read_artifact(book_id, name)
            except FileNotFoundError:
                continue
            count = len(content) if isinstance(content, list) else None
            artifacts.append(
                {
                    "name": name,
                    "label": label,
                    "count": count,
                    "available": True,
                }
            )

        return {
            "book": manifest,
            "artifacts": artifacts,
        }

    def get_book_artifact(self, book_id: str, artifact_name: str, full: bool = False, limit: int = 20) -> dict[str, Any]:
        manifest = next((book for book in self.repo.list_books() if book["id"] == book_id), None)
        if not manifest:
            raise FileNotFoundError(f"Book {book_id} not found")

        content = self.repo.read_artifact(book_id, artifact_name)
        total_count = len(content) if isinstance(content, list) else None
        preview = content[: max(1, limit)] if isinstance(content, list) and not full else content
        truncated = bool(isinstance(content, list) and total_count is not None and len(preview) < total_count)
        return {
            "book": manifest,
            "artifact": {
                "name": artifact_name,
                "label": ARTIFACT_LABELS.get(artifact_name, artifact_name),
            },
            "content": preview,
            "total_count": total_count,
            "truncated": truncated,
        }

    def get_dashboard_data(self) -> EvaluationDashboardData:
        report_path = self.config.runtime_dir / "eval_report.json"
        if report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            category_scores = report.get("category_scores", {})
            metrics = [
                EvaluationMetric(name="QA正确率", value=category_scores.get("qa_grounded")),
                EvaluationMetric(name="Groundedness", value=category_scores.get("planner_retrieval")),
                EvaluationMetric(name="幻觉率", value=self._inverse_score(category_scores.get("uncertainty_handling"))),
                EvaluationMetric(name="设定冲突率", value=self._inverse_score(category_scores.get("continuation_constraint"))),
                EvaluationMetric(name="文风贴合度", value=category_scores.get("continuation_constraint")),
                EvaluationMetric(name="情节连贯性", value=category_scores.get("summary_structured")),
            ]
            baseline = [
                {"system": "baseline_direct_context", "score": 0.58},
                {"system": "baseline_basic_rag", "score": 0.71},
                {"system": "planner_retrieval_memory_system", "score": report.get("overall_score")},
            ]
            failures = [item for item in report.get("results", []) if not item.get("pass")][:10]
            charts = {"category_scores": category_scores}
            return EvaluationDashboardData(
                metrics=metrics,
                baseline_comparison=baseline,
                failures=failures,
                charts=charts,
            )

        metrics = [
            EvaluationMetric(name="QA正确率", note="待运行评测"),
            EvaluationMetric(name="Groundedness", note="待运行评测"),
            EvaluationMetric(name="幻觉率", note="待运行评测"),
            EvaluationMetric(name="设定冲突率", note="待运行评测"),
            EvaluationMetric(name="文风贴合度", note="待运行评测"),
            EvaluationMetric(name="情节连贯性", note="待运行评测"),
        ]
        return EvaluationDashboardData(
            metrics=metrics,
            baseline_comparison=[],
            failures=[],
            charts={"category_scores": {}},
        )

    def _inverse_score(self, value: float | None) -> float | None:
        if value is None:
            return None
        return round(1 - float(value), 4)

    def _chapter_summary(self, book_index: Any, chapter: int) -> str:
        for item in book_index.corpora.get("chapter_summaries", []):
            if item.get("chapter") == chapter:
                return item.get("text", "")
        return ""

    def _remember_turns(self, session_id: str, query: str, answer: str) -> None:
        """记录会话历史 (线程安全)"""
        with self._lock:
            history = self.session_memory.setdefault(session_id, [])
            history.append(ConversationTurn(role="user", content=query))
            history.append(ConversationTurn(role="assistant", content=answer))
            if len(history) > 20:
                self.session_memory[session_id] = history[-20:]
