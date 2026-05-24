from __future__ import annotations
import logging
import json
import hashlib
from typing import Optional, Any
from collections import Counter
from .constants import (
    PERSON_RE,
    TITLE_PERSON_RE,
    STOP_NAMES,
    BAD_NAME_ENDINGS,
)
from ..llm import MiniMaxClient
from ..extraction_models import ChapterChunkExtraction

logger = logging.getLogger(__name__)

def build_extraction_chunks(chapter_text: str, chunk_size: int = 1800, overlap: int = 250) -> list[str]:
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

def extract_structured_from_llm(
    llm_client: MiniMaxClient,
    chunk_text: str,
    book_dir: Optional[Any] = None,
    book_id: str = "",
    token_callback: Optional[Any] = None,
) -> Optional[ChapterChunkExtraction]:
    if not llm_client.enabled:
        return None
    
    # Check cache first if book_id is active
    cache_path = None
    if book_id and book_dir:
        chunk_hash = hashlib.md5(chunk_text.encode("utf-8")).hexdigest()
        cache_dir = book_dir / ".llm_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"{chunk_hash}.json"
        if cache_path.exists():
            try:
                data = json.loads(cache_path.read_text(encoding="utf-8"))
                return ChapterChunkExtraction.model_validate(data)
            except Exception as e:
                logger.warning(f"Failed to load cached extraction {cache_path}: {e}")
    
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
        response = llm_client.chat(messages, temperature=0.1, max_tokens=1500)
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
        validated = ChapterChunkExtraction.model_validate(data)
        
        # Save to cache
        if cache_path:
            try:
                cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as e:
                logger.warning(f"Failed to write extraction cache {cache_path}: {e}")
        
        return validated
    except Exception as e:
        logger.warning(f"LLM structured extraction failed: {e}", exc_info=True)
        return None

def prewarm_llm_extractions(
    llm_client: MiniMaxClient,
    chapters: list[dict[str, Any]],
    book_id: str,
    book_dir: Optional[Any] = None,
    token_callback: Optional[Any] = None,
) -> dict[int, list[ChapterChunkExtraction]]:
    """预先使用结构化 LLM 提取所有章节的角色、关系和事件，并缓存。"""
    import os
    from concurrent.futures import ThreadPoolExecutor
    import threading

    active_llm_extractions = {}
    if not llm_client.enabled:
        return active_llm_extractions

    for chapter in chapters:
        active_llm_extractions[chapter["chapter"]] = []

    temp_slots = {}
    tasks = []

    max_workers = int(os.getenv("INDEX_MAX_WORKERS", "8"))
    semaphore = threading.Semaphore(max_workers)

    def worker_task(ch_num: int, chunk_idx: int, chunk_text: str):
        with semaphore:
            try:
                ext = extract_structured_from_llm(llm_client, chunk_text, book_dir, book_id, token_callback)
                return ch_num, chunk_idx, ext
            except Exception as e:
                logger.warning(f"Error extracting chunk {chunk_idx} of chapter {ch_num}: {e}")
                return ch_num, chunk_idx, None

    for chapter in chapters:
        ch_num = chapter["chapter"]
        large_chunks = build_extraction_chunks(chapter["text"])
        temp_slots[ch_num] = [None] * len(large_chunks)
        for idx, chunk in enumerate(large_chunks):
            tasks.append((ch_num, idx, chunk))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(worker_task, ch_num, idx, chunk) for ch_num, idx, chunk in tasks]
        for fut in futures:
            try:
                ch_num, idx, ext = fut.result()
                if ext is not None:
                    temp_slots[ch_num][idx] = ext
            except Exception as e:
                logger.error(f"Future result retrieval failed: {e}")

    for ch_num, slots in temp_slots.items():
        active_llm_extractions[ch_num] = [x for x in slots if x is not None]

    return active_llm_extractions

def filter_names_with_llm(
    config: Any,
    names: list[str],
    batch_size: int = 50,
    token_callback: Optional[Any] = None,
) -> set[str]:
    """Use MiniMax LLM to filter candidate names, keeping only real person names."""
    from ..llm import MiniMaxClient

    client = MiniMaxClient(config)
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

def extract_person_names(text: str) -> list[str]:
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
