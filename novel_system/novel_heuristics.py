from __future__ import annotations

from .models import Scope
from .planner import MemoryState


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

    示例用法：
        q = query.strip()
        if "主角背景是什么" in q:
            return "根据第X章，主角的背景是..."
    """
    q = query.strip()

    # 在此处为特定小说添加规则
    # if "某个特定问题" in q:
    #     return "根据第X章的答案..."

    return None


def heuristic_continuation(query: str) -> str | None:
    """小说特定的启发式续写规则。

    此函数用于为特定小说添加快速续写响应，绕过 LLM 直接返回结果。
    可以用于：
    1. 拒绝超出设定范围的请求
    2. 提供模板化的续写响应
    3. 快速验证续写请求的合法性

    Args:
        query: 用户续写请求

    Returns:
        续写响应字符串，如果没有匹配则返回 None

    示例用法：
        if "超出设定" in query:
            return "此要求超出当前设定范围，无法续写。"
    """
    # 在此处为特定小说添加续写规则
    # if "超出设定的请求" in query:
    #     return "此要求超出当前设定范围，无法续写。"

    return None
