"""Text utility functions and regexes for novel analysis.

Provides helper functions for splitting text into sentences and scoring
sentences for event significance, along with standard regexes and constants.
"""
from __future__ import annotations

import re

# Common Chinese surnames for person name detection
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
SENTENCE_RE = re.compile(r"[^。！？!?；;\n]+[。！？!?；;]?")

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


def split_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    return [match.group(0).strip() for match in SENTENCE_RE.finditer(text) if match.group(0).strip()]


def score_event_sentence(sentence: str) -> float:
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
