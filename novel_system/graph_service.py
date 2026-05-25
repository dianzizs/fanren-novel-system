"""Graph service backed by GraphRAG projectors."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .service import NovelSystemService
from .models import Scope, CanonUpdateRequest, TimelineEvent

logger = logging.getLogger(__name__)


class GraphService(NovelSystemService):
    """Graph service using GraphRAG-derived views."""

    def get_canon(self, book_id: str, scope: Scope | None = None) -> dict[str, Any]:
        self.ensure_indexed(book_id)
        scope = scope or Scope()
        items = self._load_user_canon(book_id)
        return {"book_id": book_id, "items": items}

    def update_canon(self, book_id: str, payload: CanonUpdateRequest) -> dict[str, Any]:
        current = self._load_user_canon(book_id)
        merged = list(dict.fromkeys(current + payload.items))
        path = self._user_canon_path(book_id)
        path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"book_id": book_id, "items": merged}

    def get_timeline(self, book_id: str, scope: Scope | None = None) -> list[TimelineEvent]:
        self.ensure_indexed(book_id)
        events_data = self.timeline_projector.get_timeline(book_id)
        events = []
        for evt in events_data:
            events.append(TimelineEvent(
                chapter=evt.get("chapter", 0),
                title=evt.get("type", evt.get("id", "")),
                description=evt.get("description", evt.get("text", "")),
                participants=evt.get("participants", []),
            ))
        return events

    def get_interactive_graph(
        self,
        book_id: str,
        scope: Scope | None = None,
        *,
        center: str | None = None,
        limit: int = 18,
        density: str = "auto",
    ) -> dict[str, Any]:
        self.ensure_indexed(book_id)
        return self.graph_projector.get_interactive_graph(
            book_id=book_id,
            center=center,
            limit=max(8, min(limit, 28)),
        )

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
