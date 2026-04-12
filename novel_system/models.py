from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

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


class AskRequest(BaseModel):
    user_query: str
    scope: Scope = Field(default_factory=Scope)
    conversation_history: list[ConversationTurn] = Field(default_factory=list)
    session_id: str = "default"
    top_k: int = 6
    retrieved_text: str | None = None
    test_harness: dict[str, Any] = Field(default_factory=dict)


class ContinueRequest(BaseModel):
    user_query: str
    scope: Scope = Field(default_factory=Scope)
    conversation_history: list[ConversationTurn] = Field(default_factory=list)
    session_id: str = "default"
    desired_length: tuple[int, int] | None = None
    top_k: int = 8
    test_harness: dict[str, Any] = Field(default_factory=dict)


class CanonUpdateRequest(BaseModel):
    items: list[str]


class BookCreateRequest(BaseModel):
    title: str | None = None
    file_path: str | None = None


class BookInfo(BaseModel):
    id: str
    title: str
    source_path: str
    source: Literal["upload", "local"] = "local"
    chapter_count: int = 0
    chunk_count: int = 0
    indexed: bool = False
    indexed_at: datetime | None = None


class AskResponse(BaseModel):
    planner: PlannerOutput
    answer: str
    evidence: list[EvidenceItem]
    uncertainty: Literal["low", "medium", "high"]
    scope: Scope
    memory: dict[str, Any] = Field(default_factory=dict)


class ContinuationResponse(BaseModel):
    planner: PlannerOutput
    answer: str
    evidence: list[EvidenceItem]
    uncertainty: Literal["low", "medium", "high"]
    scope: Scope
    validation: dict[str, Any] = Field(default_factory=dict)


class TimelineEvent(BaseModel):
    chapter: int
    title: str
    description: str
    participants: list[str] = Field(default_factory=list)


class EvaluationMetric(BaseModel):
    name: str
    value: float | None = None
    note: str | None = None


class EvaluationDashboardData(BaseModel):
    metrics: list[EvaluationMetric]
    baseline_comparison: list[dict[str, Any]]
    failures: list[dict[str, Any]]
    charts: dict[str, Any]

