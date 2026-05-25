"""Manage novel-domain prompts for GraphRAG workflows."""

from __future__ import annotations

import logging
from pathlib import Path

from .paths import graphrag_prompts_dir
from ..config import AppConfig

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATES: dict[str, str] = {}


def _default_entity_extraction() -> str:
    return """你是一个中文长篇小说分析专家。请从以下文本中提取所有实体。

实体类型：
- person: 人物（包括化名、绰号、道号）
- organization: 组织（门派、宗族、势力、商会、帮派）
- location: 地点（村庄、山谷、洞府、秘境、城市）
- event: 事件（战斗、收徒、交易、逃亡、突破、试炼、阴谋）
- item: 物品（法宝、丹药、书籍、材料、信物）
- technique: 功法（法术、秘术、武技、阵法、修炼方法）
- rule: 规则（世界观规则、修炼规则、门规、禁忌）

要求：
1. 保留中文原名，不要翻译
2. 每个实体的 description 用中文简要说明其属性和上下文
3. 如果同一实体有多个名称，在 description 中列出别名
4. 只提取本文本中明确出现的实体

文本：
{input_text}
"""


def _default_claim_extraction() -> str:
    return """你是一个中文长篇小说分析专家。请从以下文本中提取所有声明(claims)。

声明指文本中明确陈述的事实、事件因果、人物动机等可验证命题。

要求：
1. 每条声明标注 subject（主语/主体）、object（宾语/对象）、claim（声明内容）
2. 标注声明类型：fact（事实）、causal（因果）、motivation（动机）
3. 保留中文原文表述

文本：
{input_text}
"""


def _default_community_report() -> str:
    return """你是一个中文长篇小说分析专家。请基于以下社区(community)中的实体和关系，生成一份社区报告。

社区包含以下实体：
{entities}

社区包含以下关系：
{relationships}

请生成一份结构化的社区报告，包含：
1. 社区主题概述（该社区关心的核心人物/事件/线索）
2. 关键实体分析
3. 关系网络特征
4. 情节发展线索

请使用中文，基于提供的证据，不要编造。
"""


def _default_summarize_descriptions() -> str:
    return """你是一个中文长篇小说分析专家。请将以下关于同一实体的多条描述合并为一条简洁、信息完整的描述。

实体名称：{entity_name}

描述列表：
{description_list}

要求：
1. 合并重复信息，保留所有独特细节
2. 保持中文原名和术语
3. 按重要性排序：身份/地位 > 外貌 > 能力 > 关系 > 其他
"""


def _default_query_system_prompt() -> str:
    return """你是一个中文长篇小说《凡人修仙传》的问答助手。

核心规则：
1. 只能使用提供的证据回答，不能编造
2. 如果证据不足，明确说"当前证据不足"
3. 答案简洁，1-3句话为主
4. 引用证据时标注出处（章节或来源）
5. 保持中文回答

证据：
{context_data}
"""


class GraphRAGPromptManager:
    """Manage novel-domain prompts for GraphRAG workflows."""

    PROMPT_FILES = {
        "entity_extraction.txt": _default_entity_extraction,
        "claim_extraction.txt": _default_claim_extraction,
        "community_report.txt": _default_community_report,
        "summarize_descriptions.txt": _default_summarize_descriptions,
        "query_system_prompt.txt": _default_query_system_prompt,
    }

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def ensure_prompts(self, book_id: str) -> dict[str, Path]:
        prompts_dir = graphrag_prompts_dir(self._config, book_id)
        prompts_dir.mkdir(parents=True, exist_ok=True)
        written: dict[str, Path] = {}
        for filename, default_fn in self.PROMPT_FILES.items():
            path = prompts_dir / filename
            if not path.exists():
                path.write_text(default_fn(), encoding="utf-8")
            written[filename] = path
        logger.info("Ensured %d prompt files for %s", len(written), book_id)
        return written

    def get_prompt(self, book_id: str, name: str) -> str | None:
        path = graphrag_prompts_dir(self._config, book_id) / name
        if path.exists():
            return path.read_text(encoding="utf-8")
        default_fn = self.PROMPT_FILES.get(name)
        if default_fn:
            return default_fn()
        return None
