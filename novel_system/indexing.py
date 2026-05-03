"""书籍索引构建与管理模块。

负责解析小说文本、构建各类索引制品（章节切片、人物卡、事件时间线等）。

关键导出：
- BookIndexRepository: 索引仓库管理类
- LoadedBookIndex: 加载后的索引数据结构

依赖关系：
- 调用 vector_store 构建向量索引
- 调用 embedding 生成文本向量
"""

from __future__ import annotations

import hashlib
import json
import logging
import pickle
import re
import shutil
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING, Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
import jieba

from .config import AppConfig
from .vector_store import FAISSVectorStore

if TYPE_CHECKING:
    from .embedding.base import EmbeddingProvider
    from .vector_store.base import BaseVectorStore

logger = logging.getLogger(__name__)


CHAPTER_RE = re.compile(r"^第\s*(\d+)\s*章\s+(.+)$", re.MULTILINE)
SENTENCE_RE = re.compile(r"[^。！？!?；;\n]+[。！？!?；;]?")
COMMON_SURNAMES = (
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    "谢邹喻柏水窦章云苏潘葛范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费岑"
    "薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元顾孟平黄和穆萧尹"
    "姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵"
    "席季麻强贾路江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯管卢"
    "莫经房裘缪解应宗丁宣邓郁单杭洪包诸左石崔吉龚程嵇邢裴陆荣翁荀羊於"
    "惠甄家封芮储靳汲松井段富巫焦巴弓牧隗山谷车侯伊宁仇栾暴甘武符刘景"
    "詹束龙叶司"
)
PERSON_RE = re.compile(rf"([{COMMON_SURNAMES}][\u4e00-\u9fff]{{1,2}})")
TITLE_PERSON_RE = re.compile(
    r"([\u4e00-\u9fff]{1,4}(?:大夫|护法|堂主|门主|师兄|师姐|师父|长老|掌柜|胖子|师叔|师伯|叔))"
)
ORG_RE = re.compile(r"([\u4e00-\u9fff]{2,8}(?:门|帮|堂|谷|峰|镇|山|院|楼))")
STOP_NAMES = {
    "自己",
    "时候",
    "这里",
    "那里",
    "他们",
    "我们",
    "你们",
    "本来",
    "终于",
    "虽然",
    "不过",
    "如果",
    "因为",
    "就是",
    "只是",
    "这个",
    "那个",
    "怎么",
    "什么",
    "不是",
    "没有",
    "可以",
    "已经",
    "只有",
    "一个",
    "一下",
    "突然",
    "立刻",
    "于是",
    "同时",
    "东西",
    "地方",
    "七玄门",
    "七绝堂",
    "神手谷",
    "彩霞山",
    "青牛镇",
}
BAD_NAME_ENDINGS = set(
    "的了呢啊呀吗吧着将会是在与及又仍把被向到进出上下来去回过后中里外前后时处所带让"
    "心一一不这也就听有也和自见看没还脸对大才等并望皱想说道做给比往走更被叫早已正用"
    "觉知该当从只已又如为何但却虽再向能需可应最都"
)

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

RULE_PATTERNS = (
    "外门",
    "内门",
    "供奉堂",
    "七绝堂",
    "记名弟子",
    "测试",
    "五年一次",
    "口诀",
    "功法",
    "修炼",
)
ALIAS_MAP = {
    "韩立": ["二愣子"],
    "韩胖子": ["三叔", "韩立三叔"],
    "三叔": ["韩胖子"],
    "墨大夫": ["墨老"],
}


@dataclass
class LoadedBookIndex:
    """加载后的书籍索引数据。

    包含书籍的元数据、章节内容、各类索引制品和向量化数据。
    """

    manifest: dict[str, Any]
    chapters: list[dict[str, Any]]
    corpora: dict[str, list[dict[str, Any]]]
    vectorizers: dict[str, TfidfVectorizer]
    matrices: dict[str, Any]
    vector_stores: dict[str, "BaseVectorStore"]


class BookIndexRepository:
    """书籍索引仓库，管理索引的构建、加载和查询。

    提供从原始文本构建索引、加载已构建索引、读取索引制品等功能。
    """

    def __init__(
        self,
        config: AppConfig,
        embedding_provider: Optional["EmbeddingProvider"] = None,
    ) -> None:
        self.config = config
        self._embedding_provider = embedding_provider
        self._cache: dict[str, LoadedBookIndex] = {}

    def list_books(self) -> list[dict[str, Any]]:
        books: list[dict[str, Any]] = []
        if not self.config.books_dir.exists():
            return books
        for manifest_path in sorted(self.config.books_dir.glob("*/manifest.json")):
            for attempt in range(3):
                try:
                    with manifest_path.open("r", encoding="utf-8") as handle:
                        books.append(json.load(handle))
                    break
                except json.JSONDecodeError:
                    if attempt == 2:
                        raise
                    time.sleep(0.01)
        return books

    def remove_book(self, book_id: str) -> None:
        """从 manifest 中移除书目"""
        book_dir = self._book_dir(book_id)
        if not book_dir.exists():
            return
        import shutil
        shutil.rmtree(book_dir)

    def update_book_manifest(self, book_id: str, manifest: dict[str, Any]) -> None:
        """更新书籍 manifest"""
        book_dir = self._book_dir(book_id)
        manifest_path = book_dir / "manifest.json"
        if not manifest_path.exists():
            return
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def ensure_book_manifest(
        self,
        book_id: str,
        title: str,
        source_path: str,
        source: str = "local",
        status: str = "pending",
        reset_existing: bool = False,
    ) -> dict[str, Any]:
        book_dir = self._book_dir(book_id)
        book_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = book_dir / "manifest.json"
        if manifest_path.exists():
            if reset_existing:
                shutil.rmtree(book_dir)
                book_dir.mkdir(parents=True, exist_ok=True)
                self._cache.pop(book_id, None)
            else:
                with manifest_path.open("r", encoding="utf-8") as handle:
                    return json.load(handle)
        manifest = {
            "id": book_id,
            "title": title,
            "source_path": source_path,
            "source": source,
            "status": status,
            "chapter_count": 0,
            "chunk_count": 0,
            "indexed": False,
            "indexed_at": None,
            "index_progress": 0.0,
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest

    def read_artifact(self, book_id: str, artifact_name: str) -> Any:
        filenames = {
            "manifest": "manifest.json",
            "chapters": "chapters.json",
            "scene_segments": "scene_segments.json",
            "character_registry": "character_registry.json",
            "chapter_chunks": "chapter_chunks.json",
            "chapter_summaries": "chapter_summaries.json",
            "event_timeline": "event_timeline.json",
            "character_card": "character_card.json",
            "relationship_graph": "relationship_graph.json",
            "world_rule": "world_rule.json",
            "canon_memory": "canon_memory.json",
            "recent_plot": "recent_plot.json",
            "style_samples": "style_samples.json",
            "vision_parse": "vision_parse.json",
        }
        filename = filenames.get(artifact_name)
        if not filename:
            raise FileNotFoundError(f"Artifact {artifact_name} is not supported")
        path = self._book_dir(book_id) / filename
        if not path.exists():
            raise FileNotFoundError(f"Artifact {artifact_name} not found for {book_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def build_from_txt(self, book_id: str, title: str, source_path: Path) -> dict[str, Any]:
        raw_text = source_path.read_text(encoding="utf-8")
        chapters = self._parse_chapters(raw_text)
        chunks = self._build_chunks(chapters)
        chapter_summaries = self._build_chapter_summaries(chapters)
        events = self._build_event_timeline(chapters, chapter_summaries)
        character_cards = self._build_character_cards(chapters)
        character_registry = self._build_character_registry(chapters, character_cards)
        relationships = self._build_relationships(chapters, character_cards)
        world_rules = self._build_world_rules(chapters)
        canon_memory = self._build_canon_memory(chapter_summaries, events)
        style_samples = self._build_style_samples(chapters)
        recent_plot = self._build_recent_plot_docs(chapters, chapter_summaries)

        corpora = {
            "chapter_chunks": chunks,
            "chapter_summaries": chapter_summaries,
            "event_timeline": events,
            "character_card": character_cards,
            "character_registry": character_registry,
            "relationship_graph": relationships,
            "world_rule": world_rules,
            "canon_memory": canon_memory,
            "recent_plot": recent_plot,
            "style_samples": style_samples,
            "vision_parse": [],
        }

        book_dir = self._book_dir(book_id)
        book_dir.mkdir(parents=True, exist_ok=True)
        (book_dir / "chapters.json").write_text(
            json.dumps(chapters, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        for name, docs in corpora.items():
            (book_dir / f"{name}.json").write_text(
                json.dumps(docs, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            payload = self._build_vector_payload(docs)
            with (book_dir / f"{name}.pkl").open("wb") as handle:
                pickle.dump(payload, handle)

        # 构建并保存向量索引（如果提供了 embedding_provider）
        has_vector_index = self._build_vector_indexes(book_id, corpora)

        manifest = {
            "id": book_id,
            "title": title,
            "source_path": str(source_path),
            "chapter_count": len(chapters),
            "chunk_count": len(chunks),
            "indexed": True,
            "indexed_at": datetime.utcnow().isoformat(),
            "has_vector_index": has_vector_index,
        }
        (book_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._cache.pop(book_id, None)
        return manifest

    def load(self, book_id: str) -> LoadedBookIndex:
        if book_id in self._cache:
            return self._cache[book_id]
        book_dir = self._book_dir(book_id)
        manifest_path = book_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Book manifest not found for {book_id}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        chapters = json.loads((book_dir / "chapters.json").read_text(encoding="utf-8"))
        corpora: dict[str, list[dict[str, Any]]] = {}
        vectorizers: dict[str, TfidfVectorizer] = {}
        matrices: dict[str, Any] = {}
        for json_path in book_dir.glob("*.json"):
            if json_path.name in {"manifest.json", "chapters.json"}:
                continue
            name = json_path.stem
            corpora[name] = json.loads(json_path.read_text(encoding="utf-8"))
            pkl_path = book_dir / f"{name}.pkl"
            if pkl_path.exists():
                with pkl_path.open("rb") as handle:
                    payload = pickle.load(handle)
                vectorizers[name] = payload["vectorizer"]
                matrices[name] = payload["matrix"]

        # 加载向量索引（使用配置的向量存储目录）
        vector_stores: dict[str, "BaseVectorStore"] = {}
        book_hash = hashlib.md5(book_id.encode()).hexdigest()[:12]
        vectors_dir = self.config.vector_store_dir / book_hash
        if vectors_dir.exists() and vectors_dir.is_dir():
            for corpus_dir in vectors_dir.iterdir():
                if not corpus_dir.is_dir():
                    continue
                corpus_name = corpus_dir.name
                try:
                    # 从 metadata.json 读取维度信息
                    metadata_path = corpus_dir / "metadata.json"
                    if not metadata_path.exists():
                        continue
                    with metadata_path.open("r", encoding="utf-8") as f:
                        metadata = json.load(f)
                    dimension = metadata.get("dimension", 512)
                    metric = metadata.get("metric", "ip")

                    # 创建并加载 FAISS 索引
                    vector_store = FAISSVectorStore(dimension=dimension, metric=metric)
                    vector_store.load(str(corpus_dir))
                    vector_stores[corpus_name] = vector_store
                    logger.info(f"Loaded vector index for {corpus_name}")
                except Exception as e:
                    logger.warning(f"Failed to load vector index for {corpus_name}: {e}")

        loaded = LoadedBookIndex(
            manifest=manifest,
            chapters=chapters,
            corpora=corpora,
            vectorizers=vectorizers,
            matrices=matrices,
            vector_stores=vector_stores,
        )
        self._cache[book_id] = loaded
        return loaded

    def _book_dir(self, book_id: str) -> Path:
        return self.config.books_dir / book_id

    def _parse_chapters(self, raw_text: str) -> list[dict[str, Any]]:
        matches = list(CHAPTER_RE.finditer(raw_text))
        chapters: list[dict[str, Any]] = []
        for index, match in enumerate(matches):
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(raw_text)
            chapter_no = int(match.group(1))
            title = match.group(2).strip()
            block = raw_text[start:end].strip()
            lines = [self._clean_line(line) for line in block.splitlines()]
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

    def _build_chunks(self, chapters: list[dict[str, Any]], chunk_size: int = 420, overlap: int = 80) -> list[dict[str, Any]]:
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

    def _build_chapter_summaries(self, chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        for chapter in chapters:
            sentences = self._split_sentences(chapter["text"])
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

    def _build_event_timeline(
        self,
        chapters: list[dict[str, Any]],
        chapter_summaries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        summary_map = {item["chapter"]: item["text"] for item in chapter_summaries}
        docs: list[dict[str, Any]] = []
        for chapter in chapters:
            sentences = self._split_sentences(chapter["text"])
            # Score sentences for event significance
            scored = []
            for sentence in sentences:
                compact = sentence.strip()
                if len(compact) < 12:
                    continue
                score = self._score_event_sentence(compact)
                scored.append((score, compact))

            # Select top 3-5 sentences by score, prioritize higher scores
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
            participants = self._extract_person_names(chapter["text"])[:6]
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

    def _build_character_cards(self, chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
        chapter_hits: dict[str, list[int]] = defaultdict(list)
        evidence_lines: dict[str, list[str]] = defaultdict(list)
        frequency: Counter[str] = Counter()
        for chapter in chapters:
            names = set(self._extract_person_names(chapter["text"]))
            for name in names:
                chapter_hits[name].append(chapter["chapter"])
            for line in chapter["paragraphs"]:
                line_names = self._extract_person_names(line)
                for name in line_names:
                    frequency[name] += 1
                    if len(evidence_lines[name]) < 6 and line not in evidence_lines[name]:
                        evidence_lines[name].append(line[:120])

        ranked_names = sorted(
            chapter_hits,
            key=lambda item: (len(chapter_hits[item]), frequency[item]),
            reverse=True,
        )[:220]
        docs: list[dict[str, Any]] = []
        for name in ranked_names:
            chapters_list = sorted(set(chapter_hits[name]))
            alias_text = "、".join(ALIAS_MAP.get(name, []))
            snippets = " ".join(evidence_lines[name][:3])
            profile = f"姓名：{name}；首次出现章节：{chapters_list[0]}；相关章节：{chapters_list[:8]}。"
            if alias_text:
                profile += f" 别名/相关称呼：{alias_text}。"
            if snippets:
                profile += f" 证据摘要：{snippets}"
            docs.append(
                {
                    "id": f"character-{name}",
                    "chapter": chapters_list[0],
                    "chapter_span": [chapters_list[0], chapters_list[-1]],
                    "title": name,
                    "target": "character_card",
                    "text": profile[:420],
                    "retrieval_text": profile[:420],  # 用于检索的文本字段
                    "name": name,
                    "canonical_name": name,  # 用于精确别名匹配
                    "aliases": ALIAS_MAP.get(name, []),
                    "chapters": chapters_list,
                    "source": f"{name}人物卡",
                }
            )
        return docs

    def _build_character_registry(
        self,
        chapters: list[dict[str, Any]],
        character_cards: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Build character registry with filtered candidates.

        Filters candidates based on three evidence types:
        - Frequency: how often the name appears
        - Chapter span: how many chapters the name appears in
        - Scene evidence: whether the name appears in event contexts

        Args:
            chapters: Parsed chapter data
            character_cards: Pre-built character cards

        Returns:
            List of character registry entries with canonical names and aliases
        """
        from .graph_name_policy import (
            GraphProfile,
            load_graph_profile,
            normalize_name_with_profile,
            get_effective_seeds_and_aliases,
        )

        # Try to load profile (uses defaults if not found)
        profile = load_graph_profile("", self.config.data_dir / "books")
        canon_seeds, alias_lookup = get_effective_seeds_and_aliases(profile)

        # Collect evidence for each candidate
        name_evidence: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "frequency": 0,
                "chapters": set(),
                "scene_count": 0,
                "aliases": set(),
            }
        )

        # Extract from chapters
        for chapter in chapters:
            text = chapter.get("text", "")
            if not text:
                continue
            names = self._extract_person_names(text)
            for name in names:
                name_evidence[name]["frequency"] += 1
                name_evidence[name]["chapters"].add(chapter["chapter"])

        # Extract from character cards (scene evidence)
        card_names = {card["name"] for card in character_cards}
        for card in character_cards:
            name = card["name"]
            if name in name_evidence:
                name_evidence[name]["scene_count"] += 1
                # Add aliases from cards
                for alias in card.get("aliases", []):
                    name_evidence[name]["aliases"].add(alias)

        # Add aliases from profile/config
        for alias, canonical in alias_lookup.items():
            if canonical in name_evidence:
                name_evidence[canonical]["aliases"].add(alias)

        # Filter candidates based on evidence
        filtered_candidates: list[dict[str, Any]] = []
        for name, evidence in name_evidence.items():
            # Skip if frequency too low (noise filter)
            if evidence["frequency"] < 2:
                continue

            # Normalize name using profile
            normalized = normalize_name_with_profile(name, card_names, profile)
            if not normalized:
                continue

            # Calculate composite score
            chapter_span = len(evidence["chapters"])
            score = (
                evidence["frequency"] * 1.0 +
                chapter_span * 2.0 +
                evidence["scene_count"] * 1.5 +
                (5.0 if name in canon_seeds else 0.0)
            )

            # Minimum threshold for inclusion
            if score < 3.0 and name not in canon_seeds:
                continue

            filtered_candidates.append({
                "id": f"reg-{name}",
                "canonical_name": normalized,
                "aliases": sorted(evidence["aliases"]),
                "frequency": evidence["frequency"],
                "chapter_span": chapter_span,
                "chapters": sorted(evidence["chapters"]),
                "scene_evidence": evidence["scene_count"] > 0,
                "score": round(score, 2),
                "is_seed": name in canon_seeds,
                "text": f"{normalized} {' '.join(sorted(evidence['aliases']))} 章节{sorted(evidence['chapters'])[:5]}",
            })

        # Sort by score and deduplicate by canonical name
        seen_canonical: set[str] = set()
        registry: list[dict[str, Any]] = []
        for candidate in sorted(filtered_candidates, key=lambda x: -x["score"]):
            canonical = candidate["canonical_name"]
            if canonical not in seen_canonical:
                seen_canonical.add(canonical)
                registry.append(candidate)

        return registry[:200]  # Limit to top 200 characters

    def _build_relationships(
        self,
        chapters: list[dict[str, Any]],
        character_cards: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        known_names = {card["name"] for card in character_cards[:100]}
        pair_counter: Counter[tuple[str, str]] = Counter()
        pair_chapters: dict[tuple[str, str], list[int]] = defaultdict(list)
        for chapter in chapters:
            names = sorted(set(name for name in self._extract_person_names(chapter["text"]) if name in known_names))
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
                }
            )
        return docs

    def _build_world_rules(self, chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        seen: set[str] = set()
        for chapter in chapters:
            for sentence in self._split_sentences(chapter["text"]):
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

    def _build_canon_memory(
        self,
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

    def _build_style_samples(self, chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
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

    def _build_recent_plot_docs(
        self,
        chapters: list[dict[str, Any]],
        chapter_summaries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        summary_map = {item["chapter"]: item["text"] for item in chapter_summaries}
        docs: list[dict[str, Any]] = []
        for chapter in chapters:
            snippets = self._split_sentences(chapter["text"])[-3:]
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

    @staticmethod
    def _tokenize_chinese(text: str) -> list[str]:
        """中文分词，用于 TF-IDF。"""
        return list(jieba.cut(text))

    def _build_vector_payload(self, docs: list[dict[str, Any]]) -> dict[str, Any]:
        """构建词级 TF-IDF 向量。"""
        texts = [doc.get("text", "") for doc in docs]
        if not any(texts):
            return {"vectorizer": None, "matrix": None}

        # 词级 TF-IDF
        vectorizer = TfidfVectorizer(
            tokenizer=self._tokenize_chinese,
            lowercase=False,
            min_df=1,
            max_features=50000,
            dtype=np.float32,
        )
        matrix = vectorizer.fit_transform(texts)
        return {"vectorizer": vectorizer, "matrix": matrix}

    def _build_faiss_index(
        self,
        docs: list[dict[str, Any]],
        embedding_provider: "EmbeddingProvider",
    ) -> Optional[FAISSVectorStore]:
        """构建 FAISS 向量索引。

        Args:
            docs: 文档列表，每个文档需包含 'id' 和 'text' 字段
            embedding_provider: Embedding Provider 实例

        Returns:
            FAISSVectorStore 实例，如果文档列表为空则返回 None
        """
        if not docs:
            return None

        # 提取 ID 和文本
        ids = [doc.get("id", f"doc-{i}") for i, doc in enumerate(docs)]
        texts = [doc.get("text", "") for doc in docs]

        if not any(texts):
            logger.warning("All documents have empty text, skipping FAISS index")
            return None

        # 计算 embeddings
        try:
            embeddings = embedding_provider.embed(texts)
        except Exception as e:
            logger.warning(f"Failed to compute embeddings: {e}")
            return None

        if not embeddings:
            logger.warning("No embeddings generated, skipping FAISS index")
            return None

        # 获取向量维度
        dimension = len(embeddings[0])

        # 创建 FAISS 索引
        vector_store = FAISSVectorStore(dimension=dimension, metric="ip")
        vector_store.add(ids=ids, vectors=embeddings, documents=docs)

        logger.info(f"Built FAISS index with {len(ids)} vectors, dimension={dimension}")
        return vector_store

    def _build_vector_indexes(self, book_id: str, corpora: dict[str, list[dict[str, Any]]]) -> bool:
        """为所有 corpus 构建并保存 FAISS 向量索引。

        Args:
            book_id: 书籍 ID
            corpora: 语料字典，key 为语料名，value 为文档列表

        Returns:
            是否有索引成功构建
        """
        has_vector_index = False
        if self._embedding_provider is None:
            return has_vector_index
        book_hash = hashlib.md5(book_id.encode()).hexdigest()[:12]
        vectors_dir = self.config.vector_store_dir / book_hash
        vectors_dir.mkdir(parents=True, exist_ok=True)
        for name, docs in corpora.items():
            if not docs:
                continue
            try:
                vector_store = self._build_faiss_index(docs, self._embedding_provider)
                if vector_store is not None:
                    corpus_vector_dir = vectors_dir / name
                    corpus_vector_dir.mkdir(parents=True, exist_ok=True)
                    vector_store.save(str(corpus_vector_dir))
                    has_vector_index = True
                    logger.info(f"Saved vector index for {name} to {corpus_vector_dir}")
            except Exception as e:
                logger.warning(f"Failed to build vector index for {name}: {e}")
        return has_vector_index

    def _build_vector_payload_for_corpus(self, book_id: str, corpus_name: str, docs: list[dict[str, Any]]) -> None:
        """为单个 corpus 构建并保存向量索引（独立调用）"""
        book_dir = self._book_dir(book_id)
        payload = self._build_vector_payload(docs)
        with (book_dir / f"{corpus_name}.pkl").open("wb") as handle:
            pickle.dump(payload, handle)

    def _clean_line(self, line: str) -> str:
        line = line.replace("\u3000", " ").strip()
        line = re.sub(r"\s+", " ", line)
        return line

    def _split_sentences(self, text: str) -> list[str]:
        return [match.group(0).strip() for match in SENTENCE_RE.finditer(text) if match.group(0).strip()]

    def _score_event_sentence(self, sentence: str) -> float:
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

    def _extract_person_names(self, text: str) -> list[str]:
        names = []
        for regex in (PERSON_RE, TITLE_PERSON_RE):
            for item in regex.findall(text):
                candidate = item.strip()
                if (
                    len(candidate) < 2
                    or candidate in STOP_NAMES
                    or candidate[-1] in BAD_NAME_ENDINGS
                    or candidate.endswith("门")
                    or candidate.endswith("帮")
                    or candidate.endswith("山")
                    or candidate.endswith("谷")
                ):
                    continue
                names.append(candidate)
        frequency = Counter(names)
        return [name for name, _ in frequency.most_common() if name not in STOP_NAMES]


def scope_filter(chapter: int, chapter_scope: list[int]) -> bool:
    if not chapter_scope:
        return True
    if len(chapter_scope) == 1:
        return chapter == chapter_scope[0]
    start, end = min(chapter_scope), max(chapter_scope)
    return start <= chapter <= end
