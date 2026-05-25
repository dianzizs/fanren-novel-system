from __future__ import annotations

import re
import threading
from collections import defaultdict
from pathlib import Path

from ..config import AppConfig
from ..indexing import BookIndexRepository
from ..llm import MiniMaxClient
from ..embedding import create_embedding_provider
from ..planner import RuleBasedPlanner, QueryRewriter, MemoryState
try:
    from ..semantic_scorer import SemanticScorer
except ImportError:
    from ..legacy.old_rag.semantic_scorer import SemanticScorer
from ..reranker import create_reranker
from ..validator import AnswerValidator, ContinuationValidator, EvidenceGate
from ..novel_heuristics import NovelConfig
from ..models import ConversationTurn, Scope
from ..graphrag_app.workspace import GraphRAGWorkspace
from ..graphrag_app.input_builder import GraphRAGInputBuilder
from ..graphrag_app.settings_builder import GraphRAGSettingsBuilder
from ..graphrag_app.prompt_manager import GraphRAGPromptManager
from ..graphrag_app.index_runner import GraphRAGIndexRunner
from ..graphrag_app.table_loader import GraphRAGTableLoader
from ..graphrag_app.table_validator import GraphRAGTableValidator
from ..graphrag_app.query_engine import GraphRAGQueryEngine
from ..graphrag_app.query_router import GraphRAGQueryRouter
from ..graphrag_app.answer_adapter import GraphRAGAnswerAdapter
from ..graphrag_app.graph_projector import GraphRAGGraphProjector
from ..graphrag_app.timeline_projector import GraphRAGTimelineProjector


class NovelSystemBase:
    """小说问答系统基类，处理对象初始化和公共属性/辅助工具函数。"""

    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or AppConfig.load()
        # Embedding Provider (本地 OpenVINO 加速) - 初始化在前
        self.embedding_provider = create_embedding_provider(self.config)
        # 传入 embedding_provider 以支持向量索引构建
        self.repo = BookIndexRepository(self.config, embedding_provider=self.embedding_provider)
        self.llm = MiniMaxClient(self.config)
        self.planner = RuleBasedPlanner()
        self.query_rewriter = QueryRewriter()
        self.session_memory: dict[str, list[ConversationTurn]] = {}
        self.token_usage: dict[str, dict[str, int]] = defaultdict(
            lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        )
        self._load_token_usage_from_disk()
        self._novel_configs: dict[str, NovelConfig] = {}  # 缓存小说配置
        # 验证层组件
        self.semantic_scorer = SemanticScorer(embedding_provider=self.embedding_provider)
        self.evidence_gate = EvidenceGate(semantic_scorer=self.semantic_scorer)
        self.answer_validator = AnswerValidator()
        self.continuation_validator = ContinuationValidator()
        self.reranker = create_reranker(self.config)
        # GraphRAG 组件
        self.graphrag_workspace = GraphRAGWorkspace(self.config)
        self.graphrag_input_builder = GraphRAGInputBuilder(self.config)
        self.graphrag_settings_builder = GraphRAGSettingsBuilder(self.config)
        self.graphrag_prompt_manager = GraphRAGPromptManager(self.config)
        self.graphrag_index_runner = GraphRAGIndexRunner(self.config)
        self.graphrag_table_loader = GraphRAGTableLoader(self.config)
        self.graphrag_table_validator = GraphRAGTableValidator(self.config)
        self.graphrag_query_engine = GraphRAGQueryEngine(self.config)
        self.graphrag_query_router = GraphRAGQueryRouter()
        self.graphrag_answer_adapter = GraphRAGAnswerAdapter()
        self.graph_projector = GraphRAGGraphProjector(self.config)
        self.timeline_projector = GraphRAGTimelineProjector(self.config)
        self._lock = threading.Lock()
        self.bootstrap_default_book()

    def bootstrap_default_book(self) -> None:
        self.repo.ensure_book_manifest(
            self.config.default_book_id,
            self.config.default_book_title,
            str(self.config.default_book_path),
        )

    def _render_scope(self, scope: Scope) -> str:
        if not scope.chapters:
            return "全书已索引范围"
        if len(scope.chapters) == 1:
            return f"第{scope.chapters[0]}章"
        return f"第{min(scope.chapters)}章到第{max(scope.chapters)}章"

    def _render_memory(self, memory: MemoryState) -> str:
        parts = [f"回答长度偏{memory.preferred_length}"]
        if memory.wants_evidence:
            parts.append("带证据意识")
        if memory.no_spoiler:
            parts.append("不剧透")
        if memory.scope_note:
            parts.append(memory.scope_note)
        return "；".join(parts)

    def _trim_quote(self, text: str, limit: int = 100) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        return compact[:limit] + ("…" if len(compact) > limit else "")

    def _user_canon_path(self, book_id: str) -> Path:
        self.config.runtime_dir.mkdir(parents=True, exist_ok=True)
        return self.config.runtime_dir / f"{book_id}_user_canon.json"

    def _load_user_canon(self, book_id: str) -> list[str]:
        path = self._user_canon_path(book_id)
        if not path.exists():
            return []
        import json
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_token_usage_from_disk(self) -> None:
        import json
        import logging
        books_dir = self.config.data_dir / "books"
        if books_dir.exists():
            for book_dir in books_dir.iterdir():
                if book_dir.is_dir():
                    token_file = book_dir / "token_usage.json"
                    if token_file.exists():
                        try:
                            with open(token_file, "r", encoding="utf-8") as f:
                                usage = json.load(f)
                            self.token_usage[book_dir.name] = {
                                "prompt_tokens": usage.get("prompt_tokens", 0),
                                "completion_tokens": usage.get("completion_tokens", 0),
                                "total_tokens": usage.get("total_tokens", 0),
                            }
                        except Exception as e:
                            logging.getLogger(__name__).warning(f"Failed to load token usage from {token_file}: {e}")
