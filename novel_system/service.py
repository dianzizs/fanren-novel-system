"""小说问答系统核心服务层。

提供小说内容问答、续写、索引构建等核心功能。

关键导出：
- NovelSystemService: 主服务类，由多个组件 Mixin 组合而成
- create_service: 工厂函数，创建服务实例
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .config import AppConfig
from .models import CanonUpdateRequest, TimelineEvent, Scope
from .embedding import create_embedding_provider
from .services import (
    NovelSystemBase,
    QAServiceMixin,
    ContinuationServiceMixin,
    IndexingServiceMixin,
    StatsServiceMixin,
)

logger = logging.getLogger(__name__)


class NovelSystemService(
    QAServiceMixin,
    ContinuationServiceMixin,
    IndexingServiceMixin,
    StatsServiceMixin,
    NovelSystemBase,
):
    """小说问答系统主服务类。

    通过多重继承 Mixin 类组合问答、续写、索引构建等核心业务逻辑。
    """

    def get_canon(self, book_id: str, scope: Scope | None = None) -> dict[str, Any]:
        self.ensure_indexed(book_id)
        return {"book_id": book_id, "items": self._load_user_canon(book_id)}

    def update_canon(self, book_id: str, payload: CanonUpdateRequest) -> dict[str, Any]:
        current = self._load_user_canon(book_id)
        merged = list(dict.fromkeys(current + payload.items))
        path = self._user_canon_path(book_id)
        path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"book_id": book_id, "items": merged}

    def get_timeline(self, book_id: str, scope: Scope | None = None) -> list[TimelineEvent]:
        self.ensure_indexed(book_id)
        return self.timeline_projector.get_timeline(book_id)

    def get_reader_payload(self, book_id: str, chapter: int | None = None) -> dict[str, Any]:
        self.ensure_indexed(book_id)
        book_index = self.repo.load(book_id)
        chapters = [
            {"chapter": item["chapter"], "title": item["title"], "summary": ""}
            for item in book_index.chapters
        ]
        active = chapter or chapters[0]["chapter"]
        current = next(item for item in book_index.chapters if item["chapter"] == active)
        return {
            "book": book_index.manifest,
            "chapters": chapters,
            "current_chapter": current,
            "top_characters": [],
            "timeline": [event.model_dump() for event in self.get_timeline(book_id)][:8],
        }


def create_service() -> NovelSystemService:
    from .graph_service import GraphService
    return GraphService()
