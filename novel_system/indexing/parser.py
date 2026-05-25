from __future__ import annotations
import re
from typing import Any
from .constants import CHAPTER_RE
from ..utils.text_utils import split_sentences, score_event_sentence

CHINESE_CHAPTER_RE = re.compile(
    r"^第\s*([零〇一二两三四五六七八九十百千万\d]+)\s*章\s*(.*)$",
    re.MULTILINE,
)
_CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def _parse_chapter_number(value: str) -> int:
    if value.isdigit():
        return int(value)
    total = 0
    section = 0
    number = 0
    units = {"十": 10, "百": 100, "千": 1000, "万": 10000}
    for char in value:
        if char in _CHINESE_DIGITS:
            number = _CHINESE_DIGITS[char]
        elif char in units:
            unit = units[char]
            if unit == 10000:
                total += (section + number) * unit
                section = 0
            else:
                section += (number or 1) * unit
            number = 0
    return total + section + number


def _is_chapter_heading(line: str, number_text: str, title: str) -> bool:
    stripped = line.strip()
    return stripped in {
        f"第{number_text}章 {title}".strip(),
        f"第{number_text}章{title}".strip(),
    }

def parse_chapters(raw_text: str) -> list[dict[str, Any]]:
    matches = list(CHAPTER_RE.finditer(raw_text))
    if not matches:
        matches = list(CHINESE_CHAPTER_RE.finditer(raw_text))
    chapters: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw_text)
        chapter_no = _parse_chapter_number(match.group(1))
        title = match.group(2).strip()
        block = raw_text[start:end].strip()
        lines = [clean_line(line) for line in block.splitlines()]
        lines = [line for line in lines if line]
        if lines and _is_chapter_heading(lines[0], match.group(1), title):
            lines = lines[1:]
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
