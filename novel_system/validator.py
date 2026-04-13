"""
验证层模块

包含：
- EvidenceGate: 证据门槛，检索不到证据时拒答或降置信度
- AnswerValidator: 答案验证器，检查证据-答案一致性
- ContinuationValidator: 续写验证器，检查人物/世界/文风一致性
- SpoilerGuard: 剧透防护，自动检测剧透内容
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Optional

from pydantic import BaseModel, Field

from .models import APIWarning, EvidenceItem, Scope

if TYPE_CHECKING:
    from .semantic_scorer import SemanticScorer

logger = logging.getLogger(__name__)


# === 数据模型 ===


class EvidenceGateResult(BaseModel):
    """证据门槛结果"""
    sufficient: bool = True
    relevance_score: float = 0.0
    refusal_reason: Optional[str] = None
    confidence_adjustment: float = 1.0
    details: list[str] = Field(default_factory=list)


class AnswerValidationResult(BaseModel):
    """答案验证结果"""
    valid: bool = True
    groundedness_score: float = 0.0
    hallucination_risk: Literal["low", "medium", "high"] = "low"
    confidence: Literal["low", "medium", "high"] = "medium"
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class CharacterIssue(BaseModel):
    """人物一致性问题"""
    character: str
    issue_type: str  # "appearance", "ability", "personality", "relationship"
    expected: str
    found: str
    severity: Literal["low", "medium", "high"]


class ContinuationValidationResult(BaseModel):
    """续写验证结果"""
    valid: bool = True
    character_issues: list[str] = Field(default_factory=list)
    world_issues: list[str] = Field(default_factory=list)
    style_issues: list[str] = Field(default_factory=list)
    overall_score: float = 1.0
    details: list[str] = Field(default_factory=list)


class SpoilerRisk(BaseModel):
    """剧透风险"""
    level: Literal["none", "low", "medium", "high"] = "none"
    spoiler_content: list[str] = Field(default_factory=list)
    affected_chapters: list[int] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


# === Evidence Gate ===


class EvidenceGate:
    """
    证据门槛

    评估检索结果是否充分支持回答：
    1. 检查检索结果是否为空
    2. 计算相关性评分（语义相似度 + BM25 混合）
    3. 判断是否需要拒答
    """

    # 相关性阈值
    HIGH_RELEVANCE_THRESHOLD = 0.5
    MEDIUM_RELEVANCE_THRESHOLD = 0.3
    MIN_HITS_FOR_CONFIDENCE = 2

    def __init__(self, semantic_scorer: Optional["SemanticScorer"] = None):
        """
        初始化证据门槛

        Args:
            semantic_scorer: 语义相似度评分器（可选）
        """
        self.semantic_scorer = semantic_scorer

    def evaluate(
        self,
        query: str,
        hits: list[Any],  # list[RetrievalHit]
        scope: Scope,
    ) -> tuple[EvidenceGateResult, Optional[APIWarning]]:
        """
        评估证据是否充分支持回答

        Args:
            query: 用户查询
            hits: 检索结果列表
            scope: 章节范围

        Returns:
            tuple: (评估结果, 告警或 None)
        """
        details: list[str] = []
        warning: Optional[APIWarning] = None

        # 1. 检查空结果
        if not hits:
            return EvidenceGateResult(
                sufficient=False,
                relevance_score=0.0,
                refusal_reason="no_evidence",
                confidence_adjustment=0.0,
                details=["检索结果为空，无法提供基于证据的回答"],
            ), None

        # 2. 计算相关性评分（使用语义相似度或回退到 BM25）
        if self.semantic_scorer:
            relevance_score, warning = self.semantic_scorer.compute_similarity_with_hits(query, hits)
        else:
            relevance_score = self._compute_relevance(query, hits)
        details.append(f"相关性评分: {relevance_score:.2f}")

        # 3. 评估命中数量
        hit_count = len(hits)
        details.append(f"命中数量: {hit_count}")

        # 4. 判断充分性
        if relevance_score < self.MEDIUM_RELEVANCE_THRESHOLD:
            return EvidenceGateResult(
                sufficient=False,
                relevance_score=relevance_score,
                refusal_reason="low_relevance",
                confidence_adjustment=0.3,
                details=details + [f"相关性过低 ({relevance_score:.2f} < {self.MEDIUM_RELEVANCE_THRESHOLD})"],
            ), warning

        if hit_count < self.MIN_HITS_FOR_CONFIDENCE and relevance_score < self.HIGH_RELEVANCE_THRESHOLD:
            return EvidenceGateResult(
                sufficient=True,
                relevance_score=relevance_score,
                refusal_reason=None,
                confidence_adjustment=0.6,
                details=details + ["命中数量较少且相关性不高，建议降低置信度"],
            ), warning

        # 5. 正常情况
        confidence_adjustment = min(1.0, relevance_score * (1 + min(hit_count / 6, 0.3)))
        return EvidenceGateResult(
            sufficient=True,
            relevance_score=relevance_score,
            refusal_reason=None,
            confidence_adjustment=confidence_adjustment,
            details=details,
        ), warning

    def _compute_relevance(self, query: str, hits: list[Any]) -> float:
        """
        计算查询与检索结果的相关性评分

        使用检索结果的 score 字段加权平均
        """
        if not hits:
            return 0.0

        # 获取所有命中分数
        scores = []
        for hit in hits:
            if hasattr(hit, 'score'):
                scores.append(hit.score)
            elif isinstance(hit, dict):
                scores.append(hit.get('score', 0.0))

        if not scores:
            return 0.0

        # 加权平均，高分数的命中权重更高
        if len(scores) == 1:
            return min(1.0, scores[0] / 0.5)  # 归一化

        # 使用指数衰减权重
        weights = [0.5 ** i for i in range(len(scores))]
        total_weight = sum(weights)
        weighted_sum = sum(s * w for s, w in zip(scores, weights))

        return min(1.0, weighted_sum / total_weight / 0.5)  # 归一化


# === Answer Validator ===


class AnswerValidator:
    """
    答案验证器

    检查答案质量：
    1. 答案是否基于证据
    2. 是否存在幻觉
    3. 置信度评估
    """

    # 幻觉风险关键词
    UNCERTAINTY_PHRASES = [
        "无法确认", "查不到", "不清楚", "不知道", "难以确定",
        "没有明确", "没有具体", "无法确定", "无从考证",
    ]

    # 高置信度关键词
    HIGH_CONFIDENCE_PHRASES = [
        "明确", "确定", "肯定", "确实", "清楚",
    ]

    def validate(
        self,
        query: str,
        answer: str,
        evidence: list[EvidenceItem],
        gate_result: EvidenceGateResult,
    ) -> AnswerValidationResult:
        """
        验证答案质量

        Args:
            query: 用户查询
            answer: 生成的答案
            evidence: 证据列表
            gate_result: 证据门槛结果

        Returns:
            AnswerValidationResult: 验证结果
        """
        issues: list[str] = []
        suggestions: list[str] = []

        # 1. 检查答案中的不确定性表述
        uncertainty_detected = self._detect_uncertainty(answer)

        # 2. 检查答案是否基于证据
        groundedness_score = self._compute_groundedness(answer, evidence)

        # 3. 检测幻觉风险
        hallucination_risk = self._assess_hallucination_risk(
            answer, evidence, groundedness_score, gate_result
        )

        # 4. 计算置信度
        confidence = self._compute_confidence(
            gate_result, groundedness_score, hallucination_risk, uncertainty_detected
        )

        # 5. 收集问题和建议
        if groundedness_score < 0.5:
            issues.append(f"答案与证据相关性较低 ({groundedness_score:.2f})")
            suggestions.append("建议基于检索到的证据重新生成答案")

        if hallucination_risk == "high":
            issues.append("答案可能包含未由证据支持的内容")
            suggestions.append("请核实答案中的关键主张是否有证据支撑")

        if uncertainty_detected and gate_result.sufficient:
            issues.append("证据充分但答案表达不确定")

        valid = len(issues) == 0 or (len(issues) == 1 and uncertainty_detected and gate_result.sufficient)

        return AnswerValidationResult(
            valid=valid,
            groundedness_score=groundedness_score,
            hallucination_risk=hallucination_risk,
            confidence=confidence,
            issues=issues,
            suggestions=suggestions,
        )

    def _detect_uncertainty(self, answer: str) -> bool:
        """检测答案中的不确定性表述"""
        return any(phrase in answer for phrase in self.UNCERTAINTY_PHRASES)

    def _compute_groundedness(self, answer: str, evidence: list[EvidenceItem]) -> float:
        """
        计算答案基于证据的程度

        检查答案中的关键内容是否出现在证据中
        """
        if not evidence:
            return 0.0

        # 提取答案中的关键词
        answer_keywords = self._extract_keywords(answer)
        if not answer_keywords:
            return 0.5  # 无法提取关键词时返回中等分数

        # 检查关键词在证据中的覆盖率
        evidence_text = " ".join(e.quote for e in evidence if e.quote)
        covered = 0
        for kw in answer_keywords:
            if kw in evidence_text:
                covered += 1

        return covered / len(answer_keywords) if answer_keywords else 0.5

    def _extract_keywords(self, text: str) -> list[str]:
        """提取文本中的关键词（人名、地名、事件名等）"""
        # 使用正则提取中文词汇（2-4个字的词）
        keywords = re.findall(r'[\u4e00-\u9fa5]{2,4}', text)
        # 过滤停用词
        stopwords = {"这个", "那个", "就是", "不是", "没有", "可以", "知道", "一个", "什么", "怎么"}
        return [kw for kw in keywords if kw not in stopwords]

    def _assess_hallucination_risk(
        self,
        answer: str,
        evidence: list[EvidenceItem],
        groundedness_score: float,
        gate_result: EvidenceGateResult,
    ) -> Literal["low", "medium", "high"]:
        """评估幻觉风险"""
        # 证据不足时风险高
        if not gate_result.sufficient or gate_result.relevance_score < 0.3:
            if not any(phrase in answer for phrase in self.UNCERTAINTY_PHRASES):
                return "high"

        # 基于证据程度评估
        if groundedness_score < 0.3:
            return "high"
        elif groundedness_score < 0.6:
            return "medium"

        return "low"

    def _compute_confidence(
        self,
        gate_result: EvidenceGateResult,
        groundedness_score: float,
        hallucination_risk: Literal["low", "medium", "high"],
        uncertainty_detected: bool,
    ) -> Literal["low", "medium", "high"]:
        """计算整体置信度"""
        # 基础置信度基于证据门槛
        if not gate_result.sufficient:
            return "low"

        # 调整置信度
        score = gate_result.confidence_adjustment

        if groundedness_score > 0.7:
            score *= 1.1
        elif groundedness_score < 0.4:
            score *= 0.7

        if hallucination_risk == "high":
            score *= 0.5
        elif hallucination_risk == "medium":
            score *= 0.8

        if uncertainty_detected:
            score *= 0.9

        # 转换为置信度级别
        if score >= 0.8:
            return "low"
        elif score >= 0.5:
            return "medium"
        else:
            return "high"


# === Continuation Validator ===


class ContinuationValidator:
    """
    续写验证器

    检查续写内容的一致性：
    1. 人物一致性
    2. 世界边界
    3. 文风一致性
    """

    def validate(
        self,
        continuation: str,
        character_cards: list[dict[str, Any]],
        world_rules: list[dict[str, Any]],
        style_samples: list[str],
        scope: Scope,
    ) -> ContinuationValidationResult:
        """
        验证续写内容

        Args:
            continuation: 续写内容
            character_cards: 人物卡列表
            world_rules: 世界规则列表
            style_samples: 风格样本列表
            scope: 章节范围

        Returns:
            ContinuationValidationResult: 验证结果
        """
        character_issues = self.check_character_consistency(continuation, character_cards, scope)
        world_issues = self.check_world_boundary(continuation, world_rules, scope)
        style_issues = self.check_style_consistency(continuation, style_samples)

        # 计算总体评分
        total_issues = len(character_issues) + len(world_issues) + len(style_issues)
        overall_score = max(0.0, 1.0 - total_issues * 0.15)

        details = []
        if character_issues:
            details.append(f"人物一致性问题: {len(character_issues)} 个")
        if world_issues:
            details.append(f"世界边界问题: {len(world_issues)} 个")
        if style_issues:
            details.append(f"文风问题: {len(style_issues)} 个")

        return ContinuationValidationResult(
            valid=overall_score >= 0.6,
            character_issues=character_issues,
            world_issues=world_issues,
            style_issues=style_issues,
            overall_score=overall_score,
            details=details,
        )

    def check_character_consistency(
        self,
        continuation: str,
        character_cards: list[dict[str, Any]],
        scope: Scope,
    ) -> list[str]:
        """
        检查人物一致性

        检查项：
        1. 人物特征是否一致（外貌、能力、性格）
        2. 人物是否出现在范围内
        """
        issues: list[str] = []

        if not character_cards:
            return issues

        # 构建人物信息映射
        character_info: dict[str, dict[str, Any]] = {}
        for card in character_cards:
            name = card.get("name", "")
            if name:
                character_info[name] = {
                    "appearance": card.get("appearance", ""),
                    "abilities": card.get("abilities", []),
                    "personality": card.get("personality", ""),
                    "chapter": card.get("chapter", 0),
                }

        # 检查续写中提及的人物
        for name, info in character_info.items():
            if name not in continuation:
                continue

            # 检查外貌描述一致性
            if info.get("appearance"):
                # 提取外貌关键词
                appearance_keywords = self._extract_appearance_keywords(info["appearance"])
                for kw in appearance_keywords:
                    if kw in continuation:
                        # 检查是否有矛盾描述
                        contradiction = self._find_contradiction(continuation, name, kw)
                        if contradiction:
                            issues.append(f"人物 '{name}' 的外貌描述可能存在矛盾：原文为 '{kw}'，续写中为 '{contradiction}'")

        return issues

    def _extract_appearance_keywords(self, appearance: str) -> list[str]:
        """提取外貌关键词"""
        keywords = []
        # 提取颜色词
        colors = re.findall(r'(黑|白|金|红|青|蓝|绿|黄|紫|灰|褐)[发须眉眼瞳肤]', appearance)
        keywords.extend(colors)
        # 提取外貌特征
        features = re.findall(r'[\u4e00-\u9fa5]{2,4}[的脸的眼的发的身的]', appearance)
        keywords.extend(features)
        return keywords

    def _find_contradiction(self, text: str, name: str, expected: str) -> Optional[str]:
        """查找矛盾描述"""
        # 简单实现：检查是否有相反的颜色描述
        color_opposites = {
            "黑": ["白", "金", "红"],
            "白": ["黑", "灰"],
            "金": ["黑", "白"],
        }

        if expected in color_opposites:
            for opposite in color_opposites[expected]:
                pattern = f"{name}[^。！？]*{opposite}[发须眉眼瞳肤]"
                if re.search(pattern, text):
                    return f"{opposite}"

        return None

    def check_world_boundary(
        self,
        continuation: str,
        world_rules: list[dict[str, Any]],
        scope: Scope,
    ) -> list[str]:
        """
        检查世界边界

        检查项：
        1. 世界规则是否被遵守
        2. 是否引入范围外的设定
        """
        issues: list[str] = []

        if not world_rules:
            return issues

        # 检查是否违反已知规则
        for rule in world_rules:
            rule_text = rule.get("text", "") or rule.get("rule", "")
            if not rule_text:
                continue

            # 简单规则检查：如果规则包含"不能"、"禁止"等，检查续写是否违反
            if any(kw in rule_text for kw in ["不能", "禁止", "不可能", "无法"]):
                # 提取规则中的关键实体
                entities = re.findall(r'[\u4e00-\u9fa5]{2,4}', rule_text)
                for entity in entities:
                    if entity in continuation:
                        # 可能违反规则
                        issues.append(f"续写可能违反规则：'{rule_text[:50]}...'")
                        break

        return issues

    def check_style_consistency(
        self,
        continuation: str,
        style_samples: list[str],
    ) -> list[str]:
        """
        检查文风一致性

        检查项：
        1. 用词习惯是否一致
        2. 句式风格是否一致
        """
        issues: list[str] = []

        if not style_samples:
            return issues

        # 提取续写的风格特征
        continuation_style = self._analyze_style(continuation)

        # 提取样本的风格特征
        sample_styles = [self._analyze_style(sample) for sample in style_samples if sample]

        if not sample_styles:
            return issues

        # 比较风格差异
        avg_sentence_length = sum(s.get("avg_sentence_length", 0) for s in sample_styles) / len(sample_styles)
        cont_sentence_length = continuation_style.get("avg_sentence_length", 0)

        # 如果句子长度差异过大
        if avg_sentence_length > 0 and abs(cont_sentence_length - avg_sentence_length) > avg_sentence_length * 0.5:
            issues.append(f"句子长度风格差异较大：原文平均 {avg_sentence_length:.1f} 字，续写平均 {cont_sentence_length:.1f} 字")

        return issues

    def _analyze_style(self, text: str) -> dict[str, Any]:
        """分析文本风格"""
        # 计算平均句子长度
        sentences = re.split(r'[。！？]', text)
        sentences = [s for s in sentences if s.strip()]
        avg_length = sum(len(s) for s in sentences) / len(sentences) if sentences else 0

        return {
            "avg_sentence_length": avg_length,
            "sentence_count": len(sentences),
        }


# === Spoiler Guard ===


class SpoilerGuard:
    """
    剧透防护

    自动检测和消除剧透内容：
    1. 检测是否提及未来章节的关键事件
    2. 评估剧透风险级别
    3. 提供消除建议
    """

    # 未来事件关键词（通常指向剧透）
    FUTURE_KEYWORDS = [
        "最终", "结局", "后来", "以后", "最后",
        "真相", "原来", "到底", "终于", "成功",
    ]

    # 关键剧情关键词（剧透敏感）
    PLOT_TWIST_KEYWORDS = [
        "背叛", "死亡", "牺牲", "觉醒", "突破",
        "获得", "发现", "揭示", "真相", "秘密",
    ]

    def detect_spoiler(
        self,
        content: str,
        scope: Scope,
        total_chapters: int,
        event_timeline: list[dict[str, Any]],
    ) -> SpoilerRisk:
        """
        自动检测剧透内容

        Args:
            content: 要检测的内容
            scope: 当前阅读范围
            total_chapters: 总章节数
            event_timeline: 事件时间线

        Returns:
            SpoilerRisk: 剧透风险评估
        """
        if not scope.chapters:
            return SpoilerRisk(level="none")

        max_read_chapter = max(scope.chapters)

        # 1. 检测未来关键词
        future_matches = self._detect_future_keywords(content)

        # 2. 检测事件时间线中的剧透
        event_spoilers = self._detect_event_spoilers(content, event_timeline, max_read_chapter)

        # 3. 检测关键剧情关键词
        plot_twist_matches = self._detect_plot_twists(content)

        # 4. 综合评估风险
        risk_level = self._assess_risk_level(
            future_matches, event_spoilers, plot_twist_matches, max_read_chapter, total_chapters
        )

        # 5. 收集剧透内容
        spoiler_content = []
        affected_chapters = []

        for match in future_matches:
            spoiler_content.append(f"未来关键词: '{match}'")

        for event in event_spoilers:
            spoiler_content.append(f"未来事件: '{event.get('title', '')}'")
            if event.get('chapter'):
                affected_chapters.append(event['chapter'])

        suggestions = []
        if risk_level in ["medium", "high"]:
            suggestions.append("建议移除或模糊处理涉及后续情节的内容")
        if risk_level == "high":
            suggestions.append("此内容可能严重影响阅读体验，强烈建议重写")

        return SpoilerRisk(
            level=risk_level,
            spoiler_content=spoiler_content,
            affected_chapters=list(set(affected_chapters)),
            suggestions=suggestions,
        )

    def _detect_future_keywords(self, content: str) -> list[str]:
        """检测未来关键词"""
        matches = []
        for kw in self.FUTURE_KEYWORDS:
            if kw in content:
                # 提取包含关键词的短语
                pattern = f'.{{0,10}}{kw}.{{0,10}}'
                found = re.findall(pattern, content)
                matches.extend([f.strip() for f in found])
        return matches

    def _detect_event_spoilers(
        self,
        content: str,
        event_timeline: list[dict[str, Any]],
        max_read_chapter: int,
    ) -> list[dict[str, Any]]:
        """检测事件时间线中的剧透"""
        spoilers = []

        for event in event_timeline:
            event_chapter = event.get('chapter', 0)
            if event_chapter <= max_read_chapter:
                continue

            event_title = event.get('title', '') or event.get('description', '')
            if not event_title:
                continue

            # 检查事件标题或描述是否出现在内容中
            if any(part in content for part in self._split_event_text(event_title)):
                spoilers.append(event)

        return spoilers

    def _split_event_text(self, text: str) -> list[str]:
        """分割事件文本为关键词"""
        # 提取重要的词语
        parts = re.findall(r'[\u4e00-\u9fa5]{2,6}', text)
        return [p for p in parts if len(p) >= 2]

    def _detect_plot_twists(self, content: str) -> list[str]:
        """检测关键剧情关键词"""
        matches = []
        for kw in self.PLOT_TWIST_KEYWORDS:
            if kw in content:
                matches.append(kw)
        return matches

    def _assess_risk_level(
        self,
        future_matches: list[str],
        event_spoilers: list[dict[str, Any]],
        plot_twist_matches: list[str],
        max_read_chapter: int,
        total_chapters: int,
    ) -> Literal["none", "low", "medium", "high"]:
        """评估风险级别"""
        # 高风险：明确提及未来章节的关键事件
        if event_spoilers:
            return "high"

        # 中风险：多个未来关键词或关键剧情词
        if len(future_matches) >= 2 or len(plot_twist_matches) >= 2:
            return "medium"

        # 低风险：单个未来关键词
        if future_matches or plot_twist_matches:
            return "low"

        return "none"

    def redact_content(
        self,
        content: str,
        spoiler_risk: SpoilerRisk,
    ) -> str:
        """
        消除剧透内容

        Args:
            content: 原始内容
            spoiler_risk: 剧透风险评估

        Returns:
            处理后的内容
        """
        if spoiler_risk.level == "none":
            return content

        if spoiler_risk.level == "high":
            # 高风险：返回警告
            return "【内容涉及后续情节，为避免剧透已隐藏】"

        if spoiler_risk.level == "medium":
            # 中风险：添加警告标记
            return f"【⚠️ 可能包含剧透】{content}"

        # 低风险：直接返回
        return content


# === 拒答模板 ===


REFUSAL_TEMPLATES = {
    "no_evidence": "抱歉，在当前阅读范围内没有找到相关的内容，无法提供准确的回答。",
    "low_relevance": "抱歉，找到的内容与问题相关性较低，无法提供可靠的回答。",
    "unknown_person": "在当前范围内，查不到这个人物的相关信息，无法据此编造细节。",
    "spoiler_detected": "这个问题涉及后续情节，为避免剧透，暂时无法回答。",
}


def get_refusal_answer(reason: str, scope: Optional[Scope] = None) -> str:
    """获取拒答答案"""
    template = REFUSAL_TEMPLATES.get(reason, "抱歉，无法回答这个问题。")
    if scope and scope.chapters:
        template += f"（当前阅读范围：第 {min(scope.chapters)}-{max(scope.chapters)} 章）"
    return template
