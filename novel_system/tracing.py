"""
Tracing infrastructure for novel_system.

Provides structured JSON logging and trace data collection for observability.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import AskTrace, ContinuationTrace

# 尝试导入 python-json-logger，如果不存在则使用基本格式
try:
    from pythonjsonlogger import jsonlogger

    HAS_JSON_LOGGER = True
except ImportError:
    HAS_JSON_LOGGER = False


class TraceLogger:
    """统一的追踪日志器 (单例模式)"""

    _instance: TraceLogger | None = None
    _logger: logging.Logger
    _enabled: bool = True
    _log_level: int = logging.INFO

    def __new__(cls) -> TraceLogger:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._setup_logger()
            cls._instance._load_config()
        return cls._instance

    def _setup_logger(self) -> None:
        """配置日志器"""
        self._logger = logging.getLogger("novel_system.trace")
        self._logger.setLevel(self._log_level)

        # 避免重复添加 handler
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            if HAS_JSON_LOGGER:
                formatter = jsonlogger.JsonFormatter(
                    "%(timestamp)s %(level)s %(name)s %(message)s",
                    rename_fields={"levelname": "level", "name": "logger"},
                )
                handler.setFormatter(formatter)
            else:
                # 回退到简单文本格式
                formatter = logging.Formatter(
                    "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
                )
                handler.setFormatter(formatter)
            self._logger.addHandler(handler)

    def _load_config(self) -> None:
        """从环境变量加载配置"""
        self._enabled = os.getenv("TRACE_ENABLED", "true").lower() == "true"
        level_str = os.getenv("TRACE_LOG_LEVEL", "INFO").upper()
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
        }
        self._log_level = level_map.get(level_str, logging.INFO)
        self._logger.setLevel(self._log_level)

    @classmethod
    def generate_trace_id(cls) -> str:
        """生成唯一追踪 ID"""
        return f"trace_{uuid.uuid4().hex[:12]}"

    def set_enabled(self, enabled: bool) -> None:
        """启用/禁用追踪日志"""
        self._enabled = enabled

    def set_level(self, level: int) -> None:
        """设置日志级别"""
        self._log_level = level
        self._logger.setLevel(level)

    def log_ask_trace(self, trace: AskTrace) -> None:
        """记录 ask 追踪日志"""
        if not self._enabled:
            return

        log_data = {
            "trace_type": "ask",
            "trace_id": trace.trace_id,
            "book_id": trace.book_id,
            "session_id": trace.session_id,
            "timestamp": trace.timestamp.isoformat(),
            "query_original": trace.query_rewrite.original if trace.query_rewrite else None,
            "query_rewritten": trace.query_rewrite.rewritten if trace.query_rewrite else None,
            "query_expansions": trace.query_rewrite.expansions if trace.query_rewrite else [],
            "rewrite_duration_ms": trace.query_rewrite.duration_ms if trace.query_rewrite else None,
            "planner_task_type": trace.planner.task_type,
            "planner_retrieval_targets": trace.planner.retrieval_targets,
            "planner_constraints": trace.planner.constraints,
            "retrieval_targets": trace.retrieval.targets,
            "retrieval_hits_count": trace.retrieval.hits_count,
            "retrieval_duration_ms": trace.retrieval.duration_ms,
            "evidence_count": trace.evidence_count,
            "uncertainty": trace.uncertainty,
            "total_duration_ms": round(trace.total_duration_ms, 2),
        }

        if HAS_JSON_LOGGER:
            self._logger.info("ask_trace", extra=log_data)
        else:
            self._logger.info(f"ask_trace: {json.dumps(log_data, ensure_ascii=False)}")

    def log_continuation_trace(self, trace: ContinuationTrace) -> None:
        """记录续写追踪日志"""
        if not self._enabled:
            return

        log_data = {
            "trace_type": "continuation",
            "trace_id": trace.trace_id,
            "book_id": trace.book_id,
            "session_id": trace.session_id,
            "timestamp": trace.timestamp.isoformat(),
            "query_original": trace.query_rewrite.original if trace.query_rewrite else None,
            "query_rewritten": trace.query_rewrite.rewritten if trace.query_rewrite else None,
            "query_expansions": trace.query_rewrite.expansions if trace.query_rewrite else [],
            "rewrite_duration_ms": trace.query_rewrite.duration_ms if trace.query_rewrite else None,
            "planner_task_type": trace.planner.task_type,
            "planner_retrieval_targets": trace.planner.retrieval_targets,
            "planner_constraints": trace.planner.constraints,
            "retrieval_targets": trace.retrieval.targets,
            "retrieval_hits_count": trace.retrieval.hits_count,
            "retrieval_duration_ms": trace.retrieval.duration_ms,
            "evidence_count": trace.evidence_count,
            "uncertainty": trace.uncertainty,
            "validation_adjusted": trace.validation.adjusted,
            "validation_notes": trace.validation.notes,
            "total_duration_ms": round(trace.total_duration_ms, 2),
        }

        if HAS_JSON_LOGGER:
            self._logger.info("continuation_trace", extra=log_data)
        else:
            self._logger.info(f"continuation_trace: {json.dumps(log_data, ensure_ascii=False)}")


# 全局实例
trace_logger = TraceLogger()
