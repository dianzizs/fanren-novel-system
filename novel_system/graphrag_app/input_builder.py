"""Build GraphRAG input text files from novel TXT source."""

from __future__ import annotations

import logging
from pathlib import Path

from .paths import graphrag_input_dir
from ..config import AppConfig
from ..indexing.parser import parse_chapters

logger = logging.getLogger(__name__)

_ENCODINGS = ["utf-8", "gbk", "gb2312", "gb18030", "latin-1"]


def _read_text_with_fallback(source_path: Path) -> str:
    for enc in _ENCODINGS:
        try:
            return source_path.read_text(encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return source_path.read_text(encoding="utf-8", errors="replace")


class GraphRAGInputBuilder:
    """Convert novel TXT -> GraphRAG input/chapter_XXXX.txt files."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def build_from_txt(self, book_id: str, source_path: Path) -> dict:
        raw_text = _read_text_with_fallback(source_path)
        chapters = parse_chapters(raw_text)
        input_dir = graphrag_input_dir(self._config, book_id)
        input_dir.mkdir(parents=True, exist_ok=True)

        for chapter in chapters:
            idx = chapter["chapter"]
            title = chapter.get("title", "")
            text = chapter.get("text", "")
            filename = f"chapter_{idx:04d}.txt"
            content = f"# book_id: {book_id}\n# chapter_index: {idx}\n# chapter_title: {title}\n\n{text}\n"
            (input_dir / filename).write_text(content, encoding="utf-8")

        total_chars = sum(len(ch.get("text", "")) for ch in chapters)
        logger.info(
            "Built %d GraphRAG input files for %s, total chars=%d",
            len(chapters), book_id, total_chars,
        )
        return {
            "chapter_count": len(chapters),
            "input_files": len(chapters),
            "total_chars": total_chars,
        }
