from __future__ import annotations
import re
from typing import Any
from .constants import CHAPTER_RE
from ..utils.text_utils import split_sentences, score_event_sentence

def parse_chapters(raw_text: str) -> list[dict[str, Any]]:
    matches = list(CHAPTER_RE.finditer(raw_text))
    chapters: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw_text)
        chapter_no = int(match.group(1))
        title = match.group(2).strip()
        block = raw_text[start:end].strip()
        lines = [clean_line(line) for line in block.splitlines()]
        lines = [line for line in lines if line]
        if lines and lines[0].startswith(f"第{chapter_no}章"):
            lines = lines[1:]
        if lines and lines[0].startswith(f"第{chapter_no}章"):
            lines = lines[1:]
        paragraphs = [line for line in lines if line and "更新不易" not in line]
        text = "\n".join(paragraphs).strip()
        chapters.append(
            {
                "chapter": chapter_no,
                "title": title,
                "text": text,
                "paragraphs": paragraphs,
                "char_count": len(text),
            }
        )
    return chapters


def build_chunks(chapters: list[dict[str, Any]], chunk_size: int = 420, overlap: int = 80) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for chapter in chapters:
        text = chapter["text"]
        if not text:
            continue
        start = 0
        chunk_id = 0
        while start < len(text):
            end = min(len(text), start + chunk_size)
            snippet = text[start:end].strip()
            if snippet:
                chunks.append(
                    {
                        "id": f"ch{chapter['chapter']}-chunk{chunk_id}",
                        "chapter": chapter["chapter"],
                        "title": chapter["title"],
                        "target": "chapter_chunks",
                        "text": snippet,
                        "source": f"第{chapter['chapter']}章 {chapter['title']}",
                        "start": start,
                        "end": end,
                    }
                )
                chunk_id += 1
            if end >= len(text):
                break
            start = max(0, end - overlap)
    return chunks


def clean_line(line: str) -> str:
    line = line.replace("\u3000", " ").strip()
    line = re.sub(r"\s+", " ", line)
    return line
