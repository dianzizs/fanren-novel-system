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
import jieba.posseg as pseg

from .config import AppConfig
from .vector_store import FAISSVectorStore
from .utils.text_utils import split_sentences, score_event_sentence

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
    "撞退杀打飞跃跑笑怒死伤闪躲"
)

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
        self._active_llm_extractions: dict[int, list[Any]] = {}
        self._active_book_id: str = ""

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
                    logger.warning(f"JSONDecodeError reading {manifest_path}, attempt {attempt + 1}/3")
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

    @property
    def llm(self) -> "MiniMaxClient":
        from .llm import MiniMaxClient
        return MiniMaxClient(self.config)

    def _build_extraction_chunks(self, chapter_text: str, chunk_size: int = 1800, overlap: int = 250) -> list[str]:
        chunks = []
        start = 0
        while start < len(chapter_text):
            end = start + chunk_size
            chunk = chapter_text[start:end]
            chunks.append(chunk)
            if end >= len(chapter_text):
                break
            start += chunk_size - overlap
        return chunks

    def _extract_structured_from_llm(
        self,
        chunk_text: str,
        token_callback: Optional[Any] = None,
    ) -> Optional["ChapterChunkExtraction"]:
        if not self.llm.enabled:
            return None
        
        from .extraction_models import ChapterChunkExtraction
        import json
        
        system_prompt = (
            "你是一个专业的小说内容分析助手。你需要从给定的武侠/修仙小说片段中，提取出登场或被提及的所有人物（角色）、人物之间的关系、以及发生的关键事件。\n\n"
            "请务必遵守以下规则：\n"
            "1. 提取的角色姓名必须是小说中真实的人名或称呼（例如：韩立、南宫婉、墨大夫、厉飞雨）。\n"
            "2. 别名/称呼：提取角色在该段落中被提及的其他称呼或别名（例如：韩立被称为“二愣子”、“师弟”）。\n"
            "3. 排除噪音词：绝对不能提取普通名词、动作、状态、时间词或拼写错误的词语作为角色姓名（例如：“韩立撞”、“许多人”、“时间”、“成功”、“方法”等绝对不能作为角色）。\n"
            "4. 关系提取：提取本段提及的角色之间的关系（例如：韩立与墨大夫是师徒关系，韩立与厉飞雨是好友关系）。\n"
            "5. 事件提取：提取本段中发生的关键剧情事件，并标明参与者。\n\n"
            "请以严格的 JSON 格式输出，不要包含 markdown 格式标记，也不要包含任何除 JSON 外的代码或说明。格式如下：\n"
            "{\n"
            "  \"characters\": [\n"
            "    {\"name\": \"角色名\", \"aliases\": [\"别名1\", \"别名2\"], \"description\": \"特征描述\"}\n"
            "  ],\n"
            "  \"relationships\": [\n"
            "    {\"source\": \"角色A\", \"target\": \"角色B\", \"description\": \"关系描述\"}\n"
            "  ],\n"
            "  \"events\": [\n"
            "    {\"description\": \"事件描述\", \"participants\": [\"角色A\", \"角色B\"]}\n"
            "  ]\n"
            "}"
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"小说片段：\n{chunk_text}"}
        ]
        
        try:
            response = self.llm.chat(messages, temperature=0.1, max_tokens=1500)
            if token_callback and hasattr(response, 'usage') and response.usage:
                token_callback(response.usage)
            
            clean_content = response.content.strip()
            # strip ```json and ``` if present
            if clean_content.startswith("```"):
                lines = clean_content.splitlines()
                if lines[0].startswith("```json") or lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                clean_content = "\n".join(lines).strip()
            
            data = json.loads(clean_content)
            return ChapterChunkExtraction.model_validate(data)
        except Exception as e:
            logger.warning(f"LLM structured extraction failed: {e}", exc_info=True)
            return None

    def prewarm_llm_extractions(
        self,
        chapters: list[dict[str, Any]],
        book_id: str,
        token_callback: Optional[Any] = None,
    ) -> None:
        """预先使用结构化 LLM 提取所有章节的角色、关系和事件，并缓存。"""
        self._active_book_id = book_id
        self._active_llm_extractions = {}
        if not self.llm.enabled:
            return

        for chapter in chapters:
            ch_num = chapter["chapter"]
            self._active_llm_extractions[ch_num] = []
            large_chunks = self._build_extraction_chunks(chapter["text"])
            for chunk in large_chunks:
                ext = self._extract_structured_from_llm(chunk, token_callback)
                if ext:
                    self._active_llm_extractions[ch_num].append(ext)

    def build_from_txt(self, book_id: str, title: str, source_path: Path, token_callback: Optional[Any] = None) -> dict[str, Any]:
        raw_text = source_path.read_text(encoding="utf-8")
        chapters = self._parse_chapters(raw_text)
        
        # Warm up LLM extraction cache if enabled
        self.prewarm_llm_extractions(chapters, book_id, token_callback)
        
        chunks = self._build_chunks(chapters)
        chapter_summaries = self._build_chapter_summaries(chapters)
        events = self._build_event_timeline(chapters, chapter_summaries)
        character_cards = self._build_character_cards(chapters, book_id, token_callback)
        character_registry = self._build_character_registry(chapters, character_cards, book_id, token_callback)
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
        has_llm = False
        if hasattr(self, "_active_llm_extractions") and self._active_llm_extractions:
            has_llm = True

        summary_map = {item["chapter"]: item["text"] for item in chapter_summaries}
        docs: list[dict[str, Any]] = []
        for chapter in chapters:
            ch_num = chapter["chapter"]
            if has_llm and ch_num in self._active_llm_extractions and self._active_llm_extractions[ch_num]:
                ext_list = self._active_llm_extractions[ch_num]
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

    def _build_character_cards(
        self,
        chapters: list[dict[str, Any]],
        book_id: str = "",
        token_callback: Optional[Any] = None,
    ) -> list[dict[str, Any]]:
        from .graph_name_policy import load_graph_profile, resolve_aliases_with_profile, looks_like_graph_name

        profile = load_graph_profile(book_id, self.config.data_dir / "books")
        # Build {canonical: [alias, ...]} from profile's {alias: canonical} mapping
        profile_alias_map: dict[str, list[str]] = {}
        for alias, canonical in profile.aliases.items():
            profile_alias_map.setdefault(canonical, []).append(alias)

        # Check if we have LLM extractions
        has_llm = False
        if hasattr(self, "_active_llm_extractions") and self._active_llm_extractions:
            has_llm = True

        if has_llm:
            # Group characters from LLM extractions
            char_data = defaultdict(lambda: {"aliases": set(), "descriptions": set(), "chapters": set(), "frequency": 0})
            for ch_num, ext_list in self._active_llm_extractions.items():
                for ext in ext_list:
                    for char in ext.characters:
                        c_name = char.name.strip()
                        if not c_name or len(c_name) < 2 or len(c_name) > 10:
                            continue
                        
                        canonical = resolve_aliases_with_profile(c_name, profile)
                        # Filter obvious non-names unless in seeds
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

            # Build evidence lines from chapters
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

            # LLM-based noise filtering: let MiniMax classify which names are real person names
            llm_confirmed = self._filter_names_with_llm(ranked_names, token_callback=token_callback)
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
                        "retrieval_text": card_profile[:420],  # 用于检索的文本字段
                        "name": name,
                        "canonical_name": name,  # 用于精确别名匹配
                        "aliases": aliases,
                        "chapters": chapters_list,
                        "source": f"{name}人物卡",
                    }
                )
            return docs

    def _build_character_registry(
        self,
        chapters: list[dict[str, Any]],
        character_cards: list[dict[str, Any]],
        book_id: str = "",
        token_callback: Optional[Any] = None,
    ) -> list[dict[str, Any]]:
        """Build character registry with filtered candidates.

        Filters candidates based on three evidence types:
        - Frequency: how often the name appears
        - Chapter span: how many chapters the name appears in
        - Scene evidence: whether the name appears in event contexts

        Args:
            chapters: Parsed chapter data
            character_cards: Pre-built character cards
            book_id: Book identifier for loading graph profile
            token_callback: Optional callback for tracking token usage

        Returns:
            List of character registry entries with canonical names and aliases
        """
        from .graph_name_policy import (
            CandidateEvidence,
            build_candidate_evidence_from_chapters,
            filter_candidates_with_evidence,
            load_graph_profile,
            resolve_aliases_with_profile,
        )

        profile = load_graph_profile(book_id, self.config.data_dir / "books")

        # Check if we have LLM extractions
        has_llm = False
        if hasattr(self, "_active_llm_extractions") and self._active_llm_extractions:
            has_llm = True

        if has_llm:
            evidence: dict[str, CandidateEvidence] = {}
            seen_in_chapter = defaultdict(set)
            for ch_num, ext_list in self._active_llm_extractions.items():
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
            # Build evidence from chapters (frequency + chapter_span)
            evidence = build_candidate_evidence_from_chapters(
                chapters, self._extract_person_names
            )

        # Mark scene evidence from character cards
        for card in character_cards:
            name = card["name"]
            if name in evidence:
                evidence[name].has_scene_evidence = True

        if not has_llm:
            # LLM-based noise filtering: remove noise words from candidates
            llm_confirmed = self._filter_names_with_llm(list(evidence.keys()), token_callback=token_callback)
            if llm_confirmed:
                evidence = {k: v for k, v in evidence.items() if k in llm_confirmed}

        # Filter using three-evidence strategy
        filtered = filter_candidates_with_evidence(evidence, profile)

        # Build registry entries with extra fields
        registry: list[dict[str, Any]] = []
        for item in filtered:
            canonical = item["canonical_name"]
            # Find matching card for chapter info
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

    def _build_relationships(
        self,
        chapters: list[dict[str, Any]],
        character_cards: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        # Check if we have LLM extractions
        has_llm = False
        if hasattr(self, "_active_llm_extractions") and self._active_llm_extractions:
            has_llm = True

        known_names = {card["name"] for card in character_cards[:100]}

        if has_llm:
            from .graph_name_policy import load_graph_profile, resolve_aliases_with_profile
            book_id = getattr(self, "_active_book_id", "")
            profile = load_graph_profile(book_id, self.config.data_dir / "books")
            
            rel_counts = Counter()
            rel_chapters = defaultdict(list)
            rel_desc = defaultdict(set)
            
            for ch_num, ext_list in self._active_llm_extractions.items():
                for ext in ext_list:
                    for rel in ext.relationships:
                        src_canonical = resolve_aliases_with_profile(rel.source.strip(), profile)
                        tgt_canonical = resolve_aliases_with_profile(rel.target.strip(), profile)
                        
                        # Only keep relationships between known characters
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
                    }
                )
            return docs

        else:
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
        return split_sentences(text)

    def _score_event_sentence(self, sentence: str) -> float:
        return score_event_sentence(sentence)

    def _filter_names_with_llm(self, names: list[str], batch_size: int = 50, token_callback: Optional[Any] = None) -> set[str]:
        """Use MiniMax LLM to filter candidate names, keeping only real person names.

        Args:
            names: Candidate names to filter.
            batch_size: Number of names per LLM request.
            token_callback: Optional callback for tracking token usage.

        Returns:
            Set of names classified as person names. Returns all input names
            as-is if the LLM client is not available or any call fails.
        """
        from .llm import MiniMaxClient

        client = MiniMaxClient(self.config)
        if not client.enabled:
            logger.info("MINIMAX_API_KEY not configured, skipping LLM name filtering")
            return set(names)

        confirmed: set[str] = set()
        for i in range(0, len(names), batch_size):
            batch = names[i : i + batch_size]
            name_list = "、".join(batch)
            prompt = (
                "你是一个小说文本分析助手。下面是从一部小说中提取的候选人物名称列表，请判断哪些是真实的人名（包括外号、尊称），"
                "哪些是噪声词（如时间词、动词、普通名词、形容词等非人名词语）。\n\n"
                f"候选名称：{name_list}\n\n"
                "请只输出真实的人名，用顿号（、）分隔，不要输出任何其他内容。如果全部都不是人名，请输出'无'。\n\n"
                "**重要规则**：名称末尾带有动作动词（如撞、退、杀、打、飞、跃、走、跑、笑、怒、死、伤、闪、躲等）的不是人名，"
                "而是人名与动词的拼接错误。这类词必须排除。\n\n"
                "示例：\n"
                "输入：韩立、时间、南宫婉、成功、银月、方法\n"
                "输出：韩立、南宫婉、银月\n\n"
                "输入：章完、许多、准备、陈巧倩\n"
                "输出：陈巧倩\n\n"
                "输入：韩立撞、李四退、王五杀、赵六打\n"
                "输出：无\n\n"
                "输入：张三、韩立飞、银月、南宫婉笑\n"
                "输出：张三、银月"
            )
            try:
                response = client.chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=300,
                )
                # Track token usage if callback provided
                if token_callback and hasattr(response, 'usage') and response.usage:
                    token_callback(response.usage)
                result = response.content.strip()
                if result and result != "无":
                    for name in result.replace("，", "、").split("、"):
                        name = name.strip()
                        if name:
                            confirmed.add(name)
            except Exception:
                logger.warning(
                    "LLM name filtering failed for batch starting at %d, "
                    "falling back to unfiltered names",
                    i,
                    exc_info=True,
                )
                return set(names)

        return confirmed

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


LOCATION_SHIFT_RE = re.compile(r"(来到|走到|出了|进了|回到|在.+?广场|在.+?屋内)")


@dataclass
class FilterThresholds:
    """Thresholds for evidence-based candidate filtering.

    Characters below these thresholds are filtered out, unless they are
    seed characters (known canonical names from seed_aliases).
    """
    min_frequency: int = 2
    min_chapter_span: int = 1
    min_scene_count: int = 1


class CharacterRegistryBuilder:
    """Builds character registry from scene segments.

    The registry resolves aliases to canonical names, tracks
    character appearances across chapters, and filters candidates
    based on evidence (frequency, chapter span, scene count).
    """

    def __init__(
        self,
        seed_aliases: dict[str, list[str]] | None = None,
        thresholds: FilterThresholds | None = None,
    ) -> None:
        """Initialize with optional seed alias map and filter thresholds.

        Args:
            seed_aliases: Map of canonical names to their known aliases.
                         e.g., {"韩立": ["二愣子"], "墨大夫": ["墨老"]}
            thresholds: Evidence thresholds for filtering candidates.
        """
        self.seed_aliases = seed_aliases or {}
        self.thresholds = thresholds or FilterThresholds()
        self.alias_to_canonical = {
            alias: canonical
            for canonical, aliases in self.seed_aliases.items()
            for alias in aliases
        }
        # Seed characters are always kept regardless of evidence
        self.seed_canonical_names = set(self.seed_aliases.keys())

    def build(self, scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Build character registry from scene segments.

        Applies evidence-based filtering:
        - Frequency evidence: minimum number of mentions
        - Chapter span evidence: minimum number of unique chapters
        - Scene evidence: minimum number of unique scenes

        Seed characters (from seed_aliases keys) are always kept.

        Args:
            scenes: List of scene segment dicts with character mentions.

        Returns:
            List of character registry entries sorted by first appearance.
        """
        # Track raw evidence for each candidate
        raw_buckets: dict[str, dict[str, Any]] = {}
        mention_counts: dict[str, int] = {}

        for scene in scenes:
            seen_in_scene: set[str] = set()
            mentions_in_scene = scene.get("raw_character_mentions", [])
            for mention in mentions_in_scene:
                canonical = self.alias_to_canonical.get(mention, mention)
                mention_counts[canonical] = mention_counts.get(canonical, 0) + 1
                entry = raw_buckets.setdefault(
                    canonical,
                    {
                        "character_id": f"char-{canonical}",
                        "canonical_name": canonical,
                        "aliases": [],
                        "titles": [],
                        "name_variants": [canonical],
                        "first_seen_chapter": scene["chapter"],
                        "last_seen_chapter": scene["chapter"],
                        "chapters": {scene["chapter"]},
                        "evidence_scene_ids": [],
                        "co_occurring_characters": [],
                    },
                )
                if mention != canonical and mention not in entry["aliases"]:
                    entry["aliases"].append(mention)
                    entry["name_variants"].append(mention)
                entry["first_seen_chapter"] = min(entry["first_seen_chapter"], scene["chapter"])
                entry["last_seen_chapter"] = max(entry["last_seen_chapter"], scene["chapter"])
                entry["chapters"].add(scene["chapter"])
                if scene["id"] not in entry["evidence_scene_ids"]:
                    entry["evidence_scene_ids"].append(scene["id"])
                seen_in_scene.add(canonical)
            # Track co-occurring characters
            for canonical in seen_in_scene:
                others = sorted(name for name in seen_in_scene if name != canonical)
                for other in others:
                    if other not in raw_buckets[canonical]["co_occurring_characters"]:
                        raw_buckets[canonical]["co_occurring_characters"].append(other)

        # Filter candidates based on evidence thresholds
        filtered_entries: list[dict[str, Any]] = []
        for canonical, entry in raw_buckets.items():
            frequency = mention_counts.get(canonical, 0)
            chapter_span = len(entry["chapters"])
            scene_count = len(entry["evidence_scene_ids"])

            # Compute confidence based on evidence
            confidence = self._compute_confidence(frequency, chapter_span, scene_count)

            # Check if character passes evidence thresholds
            is_seed = canonical in self.seed_canonical_names
            passes_filter = (
                is_seed
                or (
                    frequency >= self.thresholds.min_frequency
                    and chapter_span >= self.thresholds.min_chapter_span
                    and scene_count >= self.thresholds.min_scene_count
                )
            )

            if passes_filter:
                filtered_entries.append({
                    "character_id": entry["character_id"],
                    "canonical_name": entry["canonical_name"],
                    "aliases": list(entry["aliases"]),
                    "titles": list(entry["titles"]),
                    "name_variants": list(entry["name_variants"]),
                    "first_seen_chapter": entry["first_seen_chapter"],
                    "last_seen_chapter": entry["last_seen_chapter"],
                    "active_range": [entry["first_seen_chapter"], entry["last_seen_chapter"]],
                    "evidence_scene_ids": list(entry["evidence_scene_ids"]),
                    "co_occurring_characters": list(entry["co_occurring_characters"]),
                    # Primary evidence fields (for backward compatibility)
                    "frequency": frequency,
                    "chapter_span": chapter_span,
                    "scene_count": scene_count,
                    # Additional detail fields
                    "frequency_evidence": frequency,
                    "chapter_span_evidence": chapter_span,
                    "scene_evidence": scene_count,
                    "confidence": round(confidence, 3),
                })

        # Sort deterministically: by first appearance, then by name for stability
        return sorted(filtered_entries, key=lambda item: (item["first_seen_chapter"], item["canonical_name"]))

    def _compute_confidence(self, frequency: int, chapter_span: int, scene_count: int) -> float:
        """Compute confidence score based on evidence.

        Higher evidence → higher confidence.
        Base confidence is 0.5, boosted by evidence.
        """
        base = 0.5
        frequency_boost = min(frequency * 0.05, 0.2)
        chapter_boost = min(chapter_span * 0.1, 0.15)
        scene_boost = min(scene_count * 0.05, 0.15)
        return min(base + frequency_boost + chapter_boost + scene_boost, 1.0)


class SceneSegmentBuilder:
    """Builds scene segments from parsed chapters.

    Scenes are split on location shifts and carry character mentions.
    Each scene gets a stable ID for cross-referencing.
    """

    def build(self, chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Build scene segments from chapters.

        Args:
            chapters: List of chapter dicts with 'chapter', 'title', 'paragraphs' keys.

        Returns:
            List of scene segment dicts with metadata.
        """
        scenes: list[dict[str, Any]] = []
        for chapter in chapters:
            current: list[str] = []
            start_index = 0
            scene_index = 0
            for paragraph_index, paragraph in enumerate(chapter.get("paragraphs", [])):
                if current and self._is_boundary(current[-1], paragraph):
                    scenes.append(
                        self._make_scene(chapter, scene_index, start_index, paragraph_index - 1, current)
                    )
                    scene_index += 1
                    current = []
                    start_index = paragraph_index
                current.append(paragraph)
            if current:
                scenes.append(
                    self._make_scene(chapter, scene_index, start_index, start_index + len(current) - 1, current)
                )
        return scenes

    def _is_boundary(self, previous: str, current: str) -> bool:
        """Detect if there's a scene boundary between paragraphs."""
        return bool(LOCATION_SHIFT_RE.search(current) and previous != current)

    def _make_scene(
        self,
        chapter: dict[str, Any],
        scene_index: int,
        start_index: int,
        end_index: int,
        paragraphs: list[str],
    ) -> dict[str, Any]:
        """Create a scene segment dict."""
        text = "\n".join(paragraphs)
        mentions = self._extract_person_names(text)
        ranked_mentions = [name for name, _ in Counter(mentions).most_common(6)]
        return {
            "id": f"ch{chapter['chapter']}-scene{scene_index}",
            "chapter": chapter["chapter"],
            "scene_index": scene_index,
            "title": chapter["title"],
            "text": text,
            "paragraph_start": start_index,
            "paragraph_end": end_index,
            "char_start": 0,
            "char_end": len(text),
            "scene_summary": text[:120],
            "major_characters": ranked_mentions[:3],
            "raw_character_mentions": ranked_mentions,
            "event_ids": [],
            "spoiler_level": "current",
            "prev_scene_id": None if scene_index == 0 else f"ch{chapter['chapter']}-scene{scene_index - 1}",
            "next_scene_id": None,
        }

    def _extract_person_names(self, text: str) -> list[str]:
        """Extract person names using POS tagging and surname patterns.

        Combines two strategies:
        1. jieba POS tagging (nr = person name) for segmentation-based detection
        2. Regex patterns (PERSON_RE, TITLE_PERSON_RE) for surname-based fallback

        Results are merged, deduplicated, and filtered.
        """
        names: list[str] = []

        # Strategy 1: jieba POS tagging — identify words tagged as person names (nr)
        for word in pseg.cut(text):
            if word.flag == "nr" and len(word.word) >= 2:
                candidate = word.word.strip()
                if (
                    candidate not in STOP_NAMES
                    and candidate[-1] not in BAD_NAME_ENDINGS
                    and not candidate.endswith(("门", "帮", "山", "谷", "功", "法"))
                ):
                    names.append(candidate)

        # Strategy 2: regex patterns (surname + title based)
        for regex in (PERSON_RE, TITLE_PERSON_RE):
            for item in regex.findall(text):
                candidate = item.strip()
                if (
                    len(candidate) < 2
                    or candidate in STOP_NAMES
                    or candidate[-1] in BAD_NAME_ENDINGS
                ):
                    continue
                if candidate.endswith("门") or candidate.endswith("帮") or candidate.endswith("山") or candidate.endswith("谷"):
                    continue
                names.append(candidate)

        frequency = Counter(names)
        return [name for name, _ in frequency.most_common() if name not in STOP_NAMES]


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


def _extract_event_sentences(text: str, max_sentences: int = 5, max_total_len: int = 120) -> str:
    """Extract event-like sentences from text.

    Scores sentences and returns top ones concatenated.
    Falls back to first part of text if no good sentences found.
    """
    sentences = split_sentences(text)
    scored = []
    for sentence in sentences:
        compact = sentence.strip()
        if len(compact) < 12:
            continue
        score = score_event_sentence(compact)
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


def build_book_artifacts(
    chapters: list[dict[str, Any]],
    seed_aliases: dict[str, list[str]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Build all artifacts from parsed chapters.

    This is the main entry point for indexing. It orchestrates:
    1. Scene segmentation
    2. Character registry building
    3. Target artifact building (chunks, events, cards)

    Args:
        chapters: List of chapter dicts with 'chapter', 'title', 'text', 'paragraphs' keys.
        seed_aliases: Optional {canonical: [alias, ...]} mapping for known characters.

    Returns:
        Dict mapping artifact names to lists of artifact dicts.
    """
    # Step 1: Build scene segments
    scenes = SceneSegmentBuilder().build(chapters)

    # Step 2: Build character registry
    registry = CharacterRegistryBuilder(seed_aliases=seed_aliases or {}).build(scenes)

    # Step 3: Build target artifacts
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
