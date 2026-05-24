from __future__ import annotations
import logging
import re
from collections import Counter, defaultdict
from typing import Any, Optional, TYPE_CHECKING

from .constants import RULE_PATTERNS, LOCATION_SHIFT_RE
from ..utils.text_utils import split_sentences, score_event_sentence
from .scene import SceneSegmentBuilder, CharacterRegistryBuilder, build_chapter_chunks
from .llm_extraction import filter_names_with_llm, extract_person_names
from ..graph_name_policy import (
    load_graph_profile,
    resolve_aliases_with_profile,
    looks_like_graph_name,
    CandidateEvidence,
    build_candidate_evidence_from_chapters,
    filter_candidates_with_evidence,
)

if TYPE_CHECKING:
    from ..config import AppConfig

logger = logging.getLogger(__name__)

def build_chapter_summaries(chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for chapter in chapters:
        sentences = split_sentences(chapter["text"])
        summary_sentences = []
        for sentence in sentences:
            compact = sentence.strip()
            if not compact or len(compact) < 10:
                continue
            summary_sentences.append(compact)
            if len("".join(summary_sentences)) >= 180 or len(summary_sentences) >= 4:
                break
        summary = " ".join(summary_sentences)[:220]
        docs.append(
            {
                "id": f"summary-{chapter['chapter']}",
                "chapter": chapter["chapter"],
                "title": chapter["title"],
                "target": "chapter_summaries",
                "text": f"第{chapter['chapter']}章《{chapter['title']}》：{summary}",
                "source": f"第{chapter['chapter']}章 {chapter['title']}",
            }
        )
    return docs

def _extract_event_sentences(text: str, max_sentences: int = 5, max_total_len: int = 120) -> str:
    sentences = split_sentences(text)
    scored = []
    for sentence in sentences:
        compact = sentence.strip()
        if len(compact) < 12:
            continue
        score = score_event_sentence(compact)
        scored.append((score, compact))

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
    events: list[dict[str, Any]] = []
    for scene in scenes:
        event_id = f"event-{scene['id']}-0"
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
            "description": event_text,
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

def build_event_timeline_from_chapters(
    chapters: list[dict[str, Any]],
    chapter_summaries: list[dict[str, Any]],
    active_llm_extractions: Optional[dict[int, list[Any]]] = None,
) -> list[dict[str, Any]]:
    has_llm = bool(active_llm_extractions)
    summary_map = {item["chapter"]: item["text"] for item in chapter_summaries}
    docs: list[dict[str, Any]] = []
    for chapter in chapters:
        ch_num = chapter["chapter"]
        if has_llm and active_llm_extractions and ch_num in active_llm_extractions and active_llm_extractions[ch_num]:
            ext_list = active_llm_extractions[ch_num]
            all_events = []
            participants_set = set()
            for ext in ext_list:
                for ev in ext.events:
                    if ev.description:
                        all_events.append(ev.description)
                    for p in ev.participants:
                        if p:
                            participants_set.add(p)
            if all_events:
                description = "；".join(all_events)
            else:
                description = summary_map.get(ch_num, "")
            participants = list(participants_set)[:6]
        else:
            sentences = split_sentences(chapter["text"])
            scored = []
            for sentence in sentences:
                compact = sentence.strip()
                if len(compact) < 12:
                    continue
                score = score_event_sentence(compact)
                scored.append((score, compact))

            scored.sort(key=lambda x: x[0], reverse=True)
            picked = []
            total_len = 0
            max_sentences = 5
            max_total_len = 260

            for score, sentence in scored:
                if len(picked) >= max_sentences:
                    break
                if total_len + len(sentence) + 1 > max_total_len:
                    break
                picked.append(sentence)
                total_len += len(sentence) + 1

            description = " ".join(picked) or summary_map.get(chapter["chapter"], "")
            participants = extract_person_names(chapter["text"])[:6]

        docs.append(
            {
                "id": f"event-{chapter['chapter']}",
                "chapter": chapter["chapter"],
                "title": chapter["title"],
                "target": "event_timeline",
                "text": f"第{chapter['chapter']}章事件：{description}",
                "description": description,
                "participants": participants,
                "source": f"第{chapter['chapter']}章 {chapter['title']}",
            }
        )
    return docs

def build_character_cards(
    registry: list[dict[str, Any]],
    scenes: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    scene_map = {scene["id"]: scene for scene in scenes}
    cards: list[dict[str, Any]] = []
    for entry in registry:
        related_events = [
            event["event_id"]
            for event in events
            if entry["canonical_name"] in event.get("participants", [])
        ]
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

def build_character_cards_from_chapters(
    chapters: list[dict[str, Any]],
    config: AppConfig,
    book_id: str = "",
    token_callback: Optional[Any] = None,
    active_llm_extractions: Optional[dict[int, list[Any]]] = None,
) -> list[dict[str, Any]]:
    profile = load_graph_profile(book_id, config.data_dir / "books")
    profile_alias_map: dict[str, list[str]] = {}
    for alias, canonical in profile.aliases.items():
        profile_alias_map.setdefault(canonical, []).append(alias)

    has_llm = bool(active_llm_extractions)

    if has_llm and active_llm_extractions:
        char_data = defaultdict(lambda: {"aliases": set(), "descriptions": set(), "chapters": set(), "frequency": 0})
        for ch_num, ext_list in active_llm_extractions.items():
            for ext in ext_list:
                for char in ext.characters:
                    c_name = char.name.strip()
                    if not c_name or len(c_name) < 2 or len(c_name) > 10:
                        continue
                    
                    canonical = resolve_aliases_with_profile(c_name, profile)
                    if not looks_like_graph_name(canonical) and canonical not in profile.character_seeds:
                        continue

                    char_data[canonical]["frequency"] += 1
                    char_data[canonical]["chapters"].add(ch_num)
                    
                    for alias in char.aliases:
                        alias_clean = alias.strip()
                        if alias_clean and alias_clean != canonical:
                            char_data[canonical]["aliases"].add(alias_clean)
                    
                    if char.description:
                        desc_clean = char.description.strip()
                        if desc_clean:
                            char_data[canonical]["descriptions"].add(desc_clean)

        evidence_lines: dict[str, list[str]] = defaultdict(list)
        for chapter in chapters:
            for line in chapter["paragraphs"]:
                for canonical, info in char_data.items():
                    names_to_check = {canonical} | info["aliases"] | set(profile_alias_map.get(canonical, []))
                    if any(name in line for name in names_to_check if name):
                        if len(evidence_lines[canonical]) < 6 and line not in evidence_lines[canonical]:
                            evidence_lines[canonical].append(line[:120])

        ranked_names = sorted(
            char_data.keys(),
            key=lambda item: (len(char_data[item]["chapters"]), char_data[item]["frequency"]),
            reverse=True,
        )[:220]

        docs: list[dict[str, Any]] = []
        for name in ranked_names:
            info = char_data[name]
            chapters_list = sorted(list(info["chapters"]))
            profile_aliases = profile_alias_map.get(name, [])
            all_aliases = sorted(list(info["aliases"] | set(profile_aliases)))
            alias_text = "、".join(all_aliases)
            desc_text = "；".join(sorted(list(info["descriptions"])))[:200]
            snippets = " ".join(evidence_lines[name][:3])
            
            card_profile = f"姓名：{name}；首次出现章节：{chapters_list[0]}；相关章节：{chapters_list[:8]}。"
            if desc_text:
                card_profile += f" 角色特征：{desc_text}。"
            if alias_text:
                card_profile += f" 别名/相关称呼：{alias_text}。"
            if snippets:
                card_profile += f" 证据摘要：{snippets}"
            
            docs.append(
                {
                    "id": f"character-{name}",
                    "chapter": chapters_list[0],
                    "chapter_span": [chapters_list[0], chapters_list[-1]],
                    "title": name,
                    "target": "character_card",
                    "text": card_profile[:420],
                    "retrieval_text": card_profile[:420],
                    "name": name,
                    "canonical_name": name,
                    "aliases": all_aliases,
                    "chapters": chapters_list,
                    "source": f"{name}人物卡",
                }
            )
        return docs

    else:
        chapter_hits: dict[str, list[int]] = defaultdict(list)
        evidence_lines: dict[str, list[str]] = defaultdict(list)
        frequency: Counter[str] = Counter()
        for chapter in chapters:
            names = set(extract_person_names(chapter["text"]))
            for name in names:
                chapter_hits[name].append(chapter["chapter"])
            for line in chapter["paragraphs"]:
                line_names = extract_person_names(line)
                for name in line_names:
                    frequency[name] += 1
                    if len(evidence_lines[name]) < 6 and line not in evidence_lines[name]:
                        evidence_lines[name].append(line[:120])

        ranked_names = sorted(
            chapter_hits,
            key=lambda item: (len(chapter_hits[item]), frequency[item]),
            reverse=True,
        )[:220]

        llm_confirmed = filter_names_with_llm(config, ranked_names, token_callback=token_callback)
        if llm_confirmed:
            ranked_names = [n for n in ranked_names if n in llm_confirmed]

        docs: list[dict[str, Any]] = []
        for name in ranked_names:
            chapters_list = sorted(set(chapter_hits[name]))
            aliases = profile_alias_map.get(name, [])
            alias_text = "、".join(aliases)
            snippets = " ".join(evidence_lines[name][:3])
            card_profile = f"姓名：{name}；首次出现章节：{chapters_list[0]}；相关章节：{chapters_list[:8]}。"
            if alias_text:
                card_profile += f" 别名/相关称呼：{alias_text}。"
            if snippets:
                card_profile += f" 证据摘要：{snippets}"
            docs.append(
                {
                    "id": f"character-{name}",
                    "chapter": chapters_list[0],
                    "chapter_span": [chapters_list[0], chapters_list[-1]],
                    "title": name,
                    "target": "character_card",
                    "text": card_profile[:420],
                    "retrieval_text": card_profile[:420],
                    "name": name,
                    "canonical_name": name,
                    "aliases": aliases,
                    "chapters": chapters_list,
                    "source": f"{name}人物卡",
                }
            )
        return docs

def build_character_registry(
    chapters: list[dict[str, Any]],
    character_cards: list[dict[str, Any]],
    config: AppConfig,
    book_id: str = "",
    token_callback: Optional[Any] = None,
    active_llm_extractions: Optional[dict[int, list[Any]]] = None,
) -> list[dict[str, Any]]:
    profile = load_graph_profile(book_id, config.data_dir / "books")
    has_llm = bool(active_llm_extractions)

    if has_llm and active_llm_extractions:
        evidence: dict[str, CandidateEvidence] = {}
        seen_in_chapter = defaultdict(set)
        for ch_num, ext_list in active_llm_extractions.items():
            for ext in ext_list:
                for char in ext.characters:
                    c_name = char.name.strip()
                    if not c_name or len(c_name) < 2 or len(c_name) > 10:
                        continue
                    
                    canonical = resolve_aliases_with_profile(c_name, profile)
                    if canonical not in evidence:
                        evidence[canonical] = CandidateEvidence()
                    
                    evidence[canonical].frequency += 1
                    if ch_num not in seen_in_chapter[canonical]:
                        evidence[canonical].chapter_span += 1
                        seen_in_chapter[canonical].add(ch_num)
    else:
        evidence = build_candidate_evidence_from_chapters(
            chapters, extract_person_names
        )

    for card in character_cards:
        name = card["name"]
        if name in evidence:
            evidence[name].has_scene_evidence = True

    if not has_llm:
        llm_confirmed = filter_names_with_llm(config, list(evidence.keys()), token_callback=token_callback)
        if llm_confirmed:
            evidence = {k: v for k, v in evidence.items() if k in llm_confirmed}

    filtered = filter_candidates_with_evidence(evidence, profile)

    registry: list[dict[str, Any]] = []
    for item in filtered:
        canonical = item["canonical_name"]
        matching_card = next(
            (c for c in character_cards if c.get("name") == canonical),
            None,
        )
        chapters_list = matching_card.get("chapters", []) if matching_card else []
        aliases = item["aliases"]

        registry.append({
            "id": f"reg-{canonical}",
            "canonical_name": canonical,
            "aliases": aliases,
            "frequency": item["frequency"],
            "chapter_span": item["chapter_span"],
            "chapters": chapters_list,
            "scene_evidence": item["scene_evidence"],
            "score": item["score"],
            "is_seed": item["is_seed"],
            "text": f"{canonical} {' '.join(aliases)} 章节{chapters_list[:5]}",
        })

    return registry[:200]

def build_relationships(
    chapters: list[dict[str, Any]],
    character_cards: list[dict[str, Any]],
    config: AppConfig,
    book_id: str = "",
    active_llm_extractions: Optional[dict[int, list[Any]]] = None,
) -> list[dict[str, Any]]:
    has_llm = bool(active_llm_extractions)
    known_names = {card["name"] for card in character_cards[:100]}

    if has_llm and active_llm_extractions:
        profile = load_graph_profile(book_id, config.data_dir / "books")
        
        rel_counts = Counter()
        rel_chapters = defaultdict(list)
        rel_desc = defaultdict(set)
        
        for ch_num, ext_list in active_llm_extractions.items():
            for ext in ext_list:
                for rel in ext.relationships:
                    src_canonical = resolve_aliases_with_profile(rel.source.strip(), profile)
                    tgt_canonical = resolve_aliases_with_profile(rel.target.strip(), profile)
                    
                    if src_canonical in known_names and tgt_canonical in known_names and src_canonical != tgt_canonical:
                        pair = tuple(sorted([src_canonical, tgt_canonical]))
                        rel_counts[pair] += 1
                        rel_chapters[pair].append(ch_num)
                        if rel.description:
                            rel_desc[pair].add(rel.description.strip())
                            
        docs: list[dict[str, Any]] = []
        for (left, right), count in rel_counts.most_common(180):
            chapters_list = sorted(set(rel_chapters[(left, right)]))
            descriptions = sorted(list(rel_desc[(left, right)]))
            if descriptions:
                desc_text = "；".join(descriptions)[:200]
                text = f"关系对：{left} 与 {right}。互动描述：{desc_text}。共同出现于章节：{chapters_list[:10]}。"
            else:
                text = (
                    f"关系对：{left} 与 {right} 在章节 {chapters_list[:10]} 共同出现 {count} 次，"
                    f"说明两者存在剧情关联。"
                )
            docs.append(
                {
                    "id": f"rel-{left}-{right}",
                    "chapter": chapters_list[0],
                    "title": f"{left} / {right}",
                    "target": "relationship_graph",
                    "text": text[:420],
                    "source": f"{left}-{right}关系",
                    "weight": count,
                }
            )
        return docs

    else:
        pair_counter: Counter[tuple[str, str]] = Counter()
        pair_chapters: dict[tuple[str, str], list[int]] = defaultdict(list)
        for chapter in chapters:
            names = sorted(set(name for name in extract_person_names(chapter["text"]) if name in known_names))
            for index, left in enumerate(names):
                for right in names[index + 1 :]:
                    pair = (left, right)
                    pair_counter[pair] += 1
                    pair_chapters[pair].append(chapter["chapter"])
        docs: list[dict[str, Any]] = []
        for (left, right), count in pair_counter.most_common(180):
            chapters_list = sorted(set(pair_chapters[(left, right)]))
            docs.append(
                {
                    "id": f"rel-{left}-{right}",
                    "chapter": chapters_list[0],
                    "title": f"{left} / {right}",
                    "target": "relationship_graph",
                    "text": (
                        f"关系对：{left} 与 {right} 在章节 {chapters_list[:10]} 共同出现 {count} 次，"
                        f"说明两者存在剧情关联。"
                    ),
                    "source": f"{left}-{right}关系",
                    "weight": count,
                }
            )
        return docs

def build_world_rules(chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for chapter in chapters:
        for sentence in split_sentences(chapter["text"]):
            compact = sentence.strip()
            if len(compact) < 10:
                continue
            if any(pattern in compact for pattern in RULE_PATTERNS) and compact not in seen:
                seen.add(compact)
                docs.append(
                    {
                        "id": f"rule-{chapter['chapter']}-{len(docs)}",
                        "chapter": chapter["chapter"],
                        "title": chapter["title"],
                        "target": "world_rule",
                        "text": compact[:220],
                        "source": f"第{chapter['chapter']}章 {chapter['title']}",
                    }
                )
            if len(docs) >= 320:
                return docs
    return docs

def build_canon_memory(
    chapter_summaries: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for item in chapter_summaries:
        docs.append(
            {
                "id": f"canon-summary-{item['chapter']}",
                "chapter": item["chapter"],
                "title": item["title"],
                "target": "canon_memory",
                "text": item["text"],
                "source": item["source"],
            }
        )
    for event in events:
        docs.append(
            {
                "id": f"canon-event-{event['chapter']}",
                "chapter": event["chapter"],
                "title": event["title"],
                "target": "canon_memory",
                "text": event["text"],
                "source": event["source"],
            }
        )
    return docs

def build_style_samples(chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for chapter in chapters:
        picked = []
        for paragraph in chapter["paragraphs"]:
            compact = paragraph.strip()
            if 30 <= len(compact) <= 180:
                picked.append(compact)
            if len(picked) >= 2:
                break
        for index, paragraph in enumerate(picked):
            docs.append(
                {
                    "id": f"style-{chapter['chapter']}-{index}",
                    "chapter": chapter["chapter"],
                    "title": chapter["title"],
                    "target": "style_samples",
                    "text": paragraph,
                    "source": f"第{chapter['chapter']}章 {chapter['title']}",
                }
            )
    return docs

def build_recent_plot_docs(
    chapters: list[dict[str, Any]],
    chapter_summaries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    summary_map = {item["chapter"]: item["text"] for item in chapter_summaries}
    docs: list[dict[str, Any]] = []
    for chapter in chapters:
        snippets = split_sentences(chapter["text"])[-3:]
        text = " ".join(sentence.strip() for sentence in snippets if sentence.strip())
        if not text:
            text = summary_map.get(chapter["chapter"], "")
        docs.append(
            {
                "id": f"recent-{chapter['chapter']}",
                "chapter": chapter["chapter"],
                "title": chapter["title"],
                "target": "recent_plot",
                "text": text[:260],
                "source": f"第{chapter['chapter']}章 {chapter['title']}",
            }
        )
    return docs

def build_book_artifacts(
    chapters: list[dict[str, Any]],
    seed_aliases: dict[str, list[str]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    scenes = SceneSegmentBuilder().build(chapters)
    registry = CharacterRegistryBuilder(seed_aliases=seed_aliases or {}).build(scenes)
    events = build_event_timeline(scenes)
    cards = build_character_cards(registry, scenes, events)

    return {
        "scene_segments": scenes,
        "character_registry": registry,
        "chapter_chunks": build_chapter_chunks(scenes),
        "chapter_summaries": [],
        "event_timeline": events,
        "character_card": cards,
        "relationship_graph": [],
        "world_rule": [],
        "canon_memory": [],
        "recent_plot": [],
        "style_samples": [],
        "vision_parse": [],
    }
