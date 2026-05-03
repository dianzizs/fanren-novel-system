"""Target artifact builders.

This module provides builders for the three primary retrieval targets:
- chapter_chunks: Text chunks with scene metadata
- event_timeline: Event entries derived from scenes
- character_card: Character cards backed by the registry
"""
from __future__ import annotations

import re
from typing import Any

# Event sentence recognition patterns
TIME_WORDS = frozenset({
    "后来", "之后", "之前", "当时", "几天后", "数日后", "半月后", "一月后",
    "这时候", "此时", "那时", "第二天", "次日", "当夜", "这天", "当日",
    "过了许久", "没多久", "不久", "终于", "然后", "接着", "随后",
})

ACTION_VERBS = frozenset({
    "发现", "决定", "选择", "杀死", "击杀", "获得", "得到", "遇到", "遇见",
    "逃离", "逃脱", "到达", "抵达", "攻击", "出手", "突破", "修炼", "炼制",
    "夺舍", "吞噬", "夺走", "抢走", "偷走", "救下", "救出", "抓住", "擒住",
    "释放", "解除", "开启", "关闭", "激活", "触发", "识破", "看穿",
    "答应", "拒绝", "同意", "提出", "宣布", "命令", "安排", "派遣",
    "背叛", "反叛", "投降", "归顺", "结盟", "合作", "交易", "交换",
})

CAUSALITY_WORDS = frozenset({
    "因为", "所以", "为了", "由于", "导致", "结果", "使得", "于是",
    "因此", "因而", "故而", "以至于", "从而", "原来", "只因",
})

CHANGE_INDICATORS = frozenset({
    "突然", "忽然", "猛然", "骤然", "竟", "竟然", "居然", "终于",
    "立刻", "马上", "瞬间", "顿时", "霎时", "顷刻", "一时间",
    "意外", "没想到", "出乎意料", "想不到",
})

PERSON_RE = re.compile(r"([赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜谢邹喻柏水窦章云苏潘葛范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯管卢莫经房裘缪解应宗丁宣邓郁单杭洪包诸左石崔吉龚程嵇邢裴陆荣翁荀羊於惠甄家封芮储靳汲松井段富巫焦巴弓牧隗山谷车侯伊宁仇栾暴甘武符刘景詹束龙叶司][一-鿿]{1,2})")
SENTENCE_RE = re.compile(r"[^。！？!?；;\n]+[。！？!?；;]?")


def build_chapter_chunks(
    scenes: list[dict[str, Any]],
    *,
    chunk_size: int = 420,
    overlap: int = 80,
) -> list[dict[str, Any]]:
    """Build chapter chunks from scene segments.

    Each chunk inherits scene metadata (major_characters, event_ids, spoiler_level).

    Args:
        scenes: List of scene segment dicts.
        chunk_size: Maximum characters per chunk.
        overlap: Character overlap between consecutive chunks.

    Returns:
        List of chunk dicts with scene metadata.
    """
    chunks: list[dict[str, Any]] = []
    for scene in scenes:
        text = scene["text"]
        start = 0
        chunk_index = 0
        while start < len(text):
            end = min(len(text), start + chunk_size)
            snippet = text[start:end].strip()
            if snippet:
                chunks.append(
                    {
                        "id": f"{scene['id']}-chunk{chunk_index}",
                        "chapter": scene["chapter"],
                        "title": scene["title"],
                        "target": "chapter_chunks",
                        "text": snippet,
                        "source": f"第{scene['chapter']}章 {scene['title']}",
                        "scene_id": scene["id"],
                        "scene_index": scene["scene_index"],
                        "chunk_index_in_scene": chunk_index,
                        "chunk_count_in_scene": None,
                        "major_characters": list(scene.get("major_characters", [])),
                        "event_ids": list(scene.get("event_ids", [])),
                        "spoiler_level": scene.get("spoiler_level", "current"),
                        "paragraph_start": scene["paragraph_start"],
                        "paragraph_end": scene["paragraph_end"],
                        "char_start": scene["char_start"] + start,
                        "char_end": scene["char_start"] + end,
                    }
                )
                chunk_index += 1
            if end >= len(text):
                break
            start = max(0, end - overlap)
        # Update chunk_count_in_scene for all chunks of this scene
        total = chunk_index
        for item in chunks[-total:]:
            item["chunk_count_in_scene"] = total
    return chunks


def _score_event_sentence(sentence: str) -> float:
    """Score a sentence for event significance.

    Higher scores indicate more event-like sentences.
    Factors: time words, action verbs, causality words, change indicators.
    """
    score = 0.0

    # Time words indicate temporal progression (key for events)
    for word in TIME_WORDS:
        if word in sentence:
            score += 2.0
            break  # Only count once per category

    # Action verbs are the core of events
    for word in ACTION_VERBS:
        if word in sentence:
            score += 3.0
            break

    # Causality words indicate cause-effect relationships
    for word in CAUSALITY_WORDS:
        if word in sentence:
            score += 1.5
            break

    # Change indicators show sudden/important changes
    for word in CHANGE_INDICATORS:
        if word in sentence:
            score += 1.5
            break

    # Contains person name - events involve characters
    if PERSON_RE.search(sentence):
        score += 1.0

    # Length bonus - very short sentences are usually not events
    if len(sentence) >= 20:
        score += 0.5

    return score


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    return [match.group(0).strip() for match in SENTENCE_RE.finditer(text) if match.group(0).strip()]


def _extract_event_sentences(text: str, max_sentences: int = 5, max_total_len: int = 120) -> str:
    """Extract event-like sentences from text.

    Scores sentences and returns top ones concatenated.
    Falls back to first part of text if no good sentences found.
    """
    sentences = _split_sentences(text)
    scored = []
    for sentence in sentences:
        compact = sentence.strip()
        if len(compact) < 12:
            continue
        score = _score_event_sentence(compact)
        scored.append((score, compact))

    # Select top sentences by score
    scored.sort(key=lambda x: x[0], reverse=True)
    picked = []
    total_len = 0

    for score, sentence in scored:
        if len(picked) >= max_sentences:
            break
        if total_len + len(sentence) + 1 > max_total_len:
            break
        picked.append(sentence)
        total_len += len(sentence) + 1

    return " ".join(picked) or text[:max_total_len]


def build_event_timeline(
    scenes: list[dict[str, Any]],
    *,
    max_events_per_scene: int = 1,
) -> list[dict[str, Any]]:
    """Build event timeline from scene segments.

    Each scene generates one event entry with participants from major_characters.

    Args:
        scenes: List of scene segment dicts.
        max_events_per_scene: Maximum events per scene (currently 1).

    Returns:
        List of event dicts linked to scenes.
    """
    events: list[dict[str, Any]] = []
    for scene in scenes:
        event_id = f"event-{scene['id']}-0"
        # Extract event sentences instead of just first 120 chars
        event_text = _extract_event_sentences(scene["text"])
        event = {
            "event_id": event_id,
            "id": event_id,
            "chapter": scene["chapter"],
            "scene_id": scene["id"],
            "title": f"第{scene['chapter']}章事件",
            "target": "event_timeline",
            "summary": event_text,
            "text": event_text,
            "description": event_text,  # Add description field for consistency
            "participants": list(scene.get("major_characters", [])),
            "location": scene["title"],
            "event_type": "scene_summary",
            "preceding_event_ids": [events[-1]["event_id"]] if events else [],
            "following_event_ids": [],
            "spoiler_level": scene.get("spoiler_level", "current"),
            "source": f"第{scene['chapter']}章 {scene['title']}",
        }
        if events:
            events[-1]["following_event_ids"] = [event_id]
        events.append(event)
    return events


def build_character_cards(
    registry: list[dict[str, Any]],
    scenes: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build character cards from registry, scenes, and events.

    Cards combine registry metadata with scene evidence and event participation.

    Args:
        registry: List of character registry entries.
        scenes: List of scene segment dicts.
        events: List of event dicts.

    Returns:
        List of character card dicts.
    """
    scene_map = {scene["id"]: scene for scene in scenes}
    cards: list[dict[str, Any]] = []
    for entry in registry:
        # Find events where this character participates
        related_events = [
            event["event_id"]
            for event in events
            if entry["canonical_name"] in event.get("participants", [])
        ]
        # Get evidence snippets from scenes
        snippets = [
            scene_map[scene_id]["text"][:120]
            for scene_id in entry.get("evidence_scene_ids", [])
            if scene_id in scene_map
        ]
        cards.append(
            {
                "id": f"character-{entry['canonical_name']}",
                "character_id": entry["character_id"],
                "canonical_name": entry["canonical_name"],
                "aliases": list(entry.get("aliases", [])),
                "titles": list(entry.get("titles", [])),
                "chapter": entry["active_range"][0],
                "chapter_span": list(entry["active_range"]),
                "active_range": list(entry["active_range"]),
                "target": "character_card",
                "summary": snippets[0] if snippets else entry["canonical_name"],
                "retrieval_text": " ".join([entry["canonical_name"], *entry.get("aliases", []), *snippets[:2]]).strip(),
                "key_scene_ids": list(entry.get("evidence_scene_ids", [])),
                "related_event_ids": related_events,
                "source": f"{entry['canonical_name']}人物卡",
            }
        )
    return cards
