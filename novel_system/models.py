from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


TaskType = Literal[
    "qa",
    "summary",
    "extract",
    "analysis",
    "continuation",
    "copyright_request",
]

RetrievalTarget = Literal[
    "chapter_chunks",
    "chapter_summaries",
    "event_timeline",
    "character_card",
    "relationship_graph",
    "world_rule",
    "canon_memory",
    "recent_plot",
    "style_samples",
    "vision_parse",
]


class Scope(BaseModel):
    chapters: list[int] = Field(default_factory=list)


class ConversationTurn(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class PlannerOutput(BaseModel):
    task_type: TaskType
    retrieval_needed: bool = True
    retrieval_targets: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)


class EvidenceItem(BaseModel):
    target: str
    chapter: int
    title: str
    score: float
    quote: str
    source: str


class APIWarning(BaseModel):
    """API 告警"""
    type: Literal["embedding_fallback", "api_error", "rate_limit"]
    message: str
    severity: Literal["info", "warning", "error"]
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


# === Trace 数据模型 ===


class QueryRewriteTrace(BaseModel):
    """查询重写追踪"""
    original: str
    rewritten: str
    expansions: list[str] = Field(default_factory=list)
    duration_ms: Optional[float] = None


class RetrievalHitTrace(BaseModel):
    """单个检索命中的简化追踪"""
    target: str
    document_id: Optional[str] = None
    chapter: Optional[int] = None
    score: float


class RetrievalTrace(BaseModel):
    """检索追踪"""
    targets: list[str]
    hits_count: int
    hits: list[RetrievalHitTrace] = Field(default_factory=list)
    duration_ms: Optional[float] = None


class EvidenceSpan(BaseModel):
    """证据片段追踪"""
    # 位置范围
    document_id: str
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    chapter: Optional[int] = None

    # 证据片段详情
    text_snippet: str
    relevance_score: float
    source_type: str


class ValidationResult(BaseModel):
    """验证结果（仅续写）"""
    adjusted: bool
    notes: list[str] = Field(default_factory=list)
    consistency_passed: bool = True


class AskTrace(BaseModel):
    """ask() 完整追踪"""
    trace_id: str
    book_id: str
    session_id: str
    timestamp: datetime
    query_rewrite: Optional[QueryRewriteTrace] = None
    planner: PlannerOutput
    retrieval: RetrievalTrace
    evidence_count: int
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    uncertainty: Literal["low", "medium", "high"]
    total_duration_ms: float
    memory_state: dict[str, Any] = Field(default_factory=dict)


class ContinuationTrace(BaseModel):
    """continue_story() 完整追踪"""
    trace_id: str
    book_id: str
    session_id: str
    timestamp: datetime
    query_rewrite: Optional[QueryRewriteTrace] = None
    planner: PlannerOutput
    retrieval: RetrievalTrace
    evidence_count: int
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    uncertainty: Literal["low", "medium", "high"]
    validation: ValidationResult
    total_duration_ms: float
    memory_state: dict[str, Any] = Field(default_factory=dict)


class AskRequest(BaseModel):
    user_query: str
    scope: Scope = Field(default_factory=Scope)
    conversation_history: list[ConversationTurn] = Field(default_factory=list)
    session_id: str = "default"
    top_k: int = 6
    retrieved_text: Optional[str] = None
    test_harness: dict[str, Any] = Field(default_factory=dict)
    debug: bool = False  # 启用追踪返回


class ContinueRequest(BaseModel):
    user_query: str
    scope: Scope = Field(default_factory=Scope)
    conversation_history: list[ConversationTurn] = Field(default_factory=list)
    session_id: str = "default"
    desired_length: Optional[tuple[int, int]] = None
    top_k: int = 8
    test_harness: dict[str, Any] = Field(default_factory=dict)
    debug: bool = False  # 启用追踪返回


class CanonUpdateRequest(BaseModel):
    items: list[str]


class BookCreateRequest(BaseModel):
    title: Optional[str] = None
    file_path: Optional[str] = None


class BookInfo(BaseModel):
    id: str
    title: str
    source_path: str
    source: Literal["upload", "local"] = "local"
    chapter_count: int = 0
    chunk_count: int = 0
    indexed: bool = False
    indexed_at: Optional[datetime] = None
    status: Literal["pending", "indexing", "ready", "error"] = "pending"
    index_progress: float = 0.0


class AskResponse(BaseModel):
    planner: PlannerOutput
    answer: str
    evidence: list[EvidenceItem]
    uncertainty: Literal["low", "medium", "high"]
    scope: Scope
    memory: dict[str, Any] = Field(default_factory=dict)
    warnings: list[APIWarning] = Field(default_factory=list)
    trace: Optional[AskTrace] = None  # 可选追踪数据


class ContinuationResponse(BaseModel):
    planner: PlannerOutput
    answer: str
    evidence: list[EvidenceItem]
    uncertainty: Literal["low", "medium", "high"]
    scope: Scope
    validation: dict[str, Any] = Field(default_factory=dict)
    trace: Optional[ContinuationTrace] = None  # 可选追踪数据


class TimelineEvent(BaseModel):
    chapter: int
    title: str
    description: str
    participants: list[str] = Field(default_factory=list)


class EvaluationMetric(BaseModel):
    name: str
    value: Optional[float] = None
    note: Optional[str] = None


class EvaluationDashboardData(BaseModel):
    metrics: list[EvaluationMetric]
    baseline_comparison: list[dict[str, Any]]
    failures: list[dict[str, Any]]
    charts: dict[str, Any]


class TokenStats(BaseModel):
    """Token usage statistics for a book"""
    book_id: str
    title: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class TokenStatsSummary(BaseModel):
    """Overall token usage statistics"""
    books: list[TokenStats]
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0

