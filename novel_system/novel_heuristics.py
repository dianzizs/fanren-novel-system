"""
小说特定配置和启发式规则。

这个模块存放与特定小说相关的内容：
- 角色特征描述
- 续写模板
- 快速响应规则

通用逻辑应该放在 service.py 里，只有小说特定的内容放在这里。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import Scope
from .planner import MemoryState


@dataclass
class NovelConfig:
    """小说配置 - 存储小说特定的设置"""

    # 基础信息
    book_id: str = ""
    title: str = ""

    # 主要角色及其特征（用于续写 prompt）
    # 格式: {"角色名": "特征描述"}
    character_traits: dict[str, str] = field(default_factory=dict)

    # 续写时的注意事项
    continuation_notes: list[str] = field(default_factory=list)

    # 禁止出现的内容（超出设定、现代用语等）
    forbidden_patterns: list[str] = field(default_factory=list)

    def get_character_prompt(self) -> str:
        """生成角色特征的 prompt 片段"""
        if not self.character_traits:
            return "保持人物性格一致。"
        parts = [f"{name}{trait}" for name, trait in self.character_traits.items()]
        return "；".join(parts) + "。"


# ── 小说配置注册表 ──────────────────────────────────────────────

NOVEL_CONFIGS: dict[str, NovelConfig] = {
    "fanrenxiuchuan": NovelConfig(
        book_id="fanrenxiuchuan",
        title="凡人修仙传",
        character_traits={
            "韩立": "谨慎、好奇、克制",
            "张铁": "憨厚直率",
        },
        continuation_notes=[
            "不要剧透后文",
            "不能突然跳战力",
        ],
        forbidden_patterns=[
            "绝世神丹", "横扫", "无敌", "秒杀",
            "筑基", "金丹", "元婴", "飞升",
        ],
    ),
}


def get_novel_config(book_id: str) -> NovelConfig:
    """获取小说配置，如果不存在返回默认配置"""
    return NOVEL_CONFIGS.get(book_id, NovelConfig(book_id=book_id))


def extract_character_traits_from_index(corpora: dict[str, list[dict]]) -> dict[str, str]:
    """从索引数据动态提取角色特征

    这个函数会分析人物卡，提取关键词来描述角色特征。
    当 NOVEL_CONFIGS 中没有配置时，使用这个方法动态生成。
    """
    traits = {}

    character_cards = corpora.get("character_card", [])
    for card in character_cards[:10]:  # 只看前 10 个主要角色
        name = card.get("name", "")
        if not name or len(name) > 4:  # 过滤无效名称
            continue

        text = card.get("text", "").lower()
        card_traits = []

        # 从文本中提取特征关键词
        trait_keywords = {
            "谨慎": ["谨慎", "小心", "警惕", "戒备"],
            "聪明": ["聪明", "机敏", "精明", "智慧"],
            "憨厚": ["憨厚", "老实", "朴实", "忠厚"],
            "直率": ["直率", "爽快", "耿直"],
            "阴险": ["阴险", "狡诈", "城府"],
            "冷静": ["冷静", "沉稳", "镇定"],
        }

        for trait, keywords in trait_keywords.items():
            if any(kw in text for kw in keywords):
                card_traits.append(trait)

        if card_traits:
            traits[name] = "、".join(card_traits[:2])  # 最多 2 个特征

    return traits


# ── 启发式规则 ──────────────────────────────────────────────

def heuristic_answer(query: str, scope: Scope, memory: MemoryState) -> str | None:
    """小说特定的启发式问答规则。

    此函数用于为特定小说添加快速响应规则，绕过 LLM 直接返回答案。
    这是可选的优化，如果查询匹配已知问题，可以立即返回结果。

    Args:
        query: 用户查询
        scope: 章节范围
        memory: 记忆状态

    Returns:
        匹配的答案字符串，如果没有匹配则返回 None
    """
    q = query.strip()
    # 在此处为特定小说添加规则
    return None


def heuristic_continuation(query: str, config: NovelConfig | None = None) -> str | None:
    """小说特定的启发式续写规则。

    Args:
        query: 用户续写请求
        config: 小说配置（可选）

    Returns:
        续写响应字符串，如果没有匹配则返回 None
    """
    if config is None:
        return None

    q = query.strip()

    # 检查是否包含禁止的模式
    for pattern in config.forbidden_patterns:
        if pattern in q:
            return (
                f"这个要求已经超出了当前已知设定范围，"
                f"我不能直接按'{pattern}'相关的内容去写。"
                f"如果仍按当前范围续写，需要调整为符合当前设定的版本。"
            )

    return None


def get_continuation_template(config: NovelConfig | None = None) -> str:
    """获取续写的模板文本

    当 LLM 不可用时，使用这个模板作为 fallback。
    应该根据小说配置动态生成，而不是硬编码。
    """
    if config and config.character_traits:
        # 有配置时，生成角色相关的模板
        main_char = next(iter(config.character_traits.keys()), "主角")
        trait = next(iter(config.character_traits.values()), "谨慎")
        return (
            f"{main_char}仔细观察着周围的一切，心中暗自盘算。"
            f"虽然还有很多不确定的地方，但{trait}的性格让他决定先观望再说。"
            f"他不动声色地将这件事记在心里，准备找机会慢慢弄清楚。"
        )

    # 通用模板
    return (
        "主角仔细观察着眼前的一切，心中暗自盘算。"
        "虽然还有很多不确定的地方，但谨慎的性格让他决定先观望再说。"
        "他不动声色地将这件事记在心里，准备找机会慢慢弄清楚。"
    )


def get_safe_continuation_template(scope_desc: str = "当前范围") -> str:
    """获取安全续写的模板（当用户要求越界时）

    Args:
        scope_desc: 范围描述，如"前14章"
    """
    return (
        f"这个要求已经超出了{scope_desc}里已知的设定范围，"
        f"我不能直接按照那个方向去写。"
        f"如果仍按当前范围续写，需要调整为符合当前设定的版本。"
    )
