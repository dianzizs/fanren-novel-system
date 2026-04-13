# 验证层优化方案

## 概述

本文档详细说明四个优化方向的实现方案，包括代码改动、新增文件和测试计划。

---

## 优化一：EvidenceGate 语义相似度

### 问题分析

**当前实现**：仅使用 BM25 分数计算相关性，无法理解语义。

```python
# validator.py:155-184
def _compute_relevance(self, query: str, hits: list[Any]) -> float:
    scores = [hit.score for hit in hits]
    weighted_sum = sum(s * w for s, w in zip(scores, weights))
    return min(1.0, weighted_sum / total_weight / 0.5)
```

**典型失败案例**：

| 查询 | 检索到的文本 | BM25 分数 | 实际相关性 |
|------|-------------|----------|-----------|
| "主角的成名绝技" | "韩立施展青元剑诀..." | 0.12（低） | ✅ 高 |
| "那个小绿瓶的作用" | "掌天瓶是仙界至宝..." | 0.28（低） | ✅ 高 |
| "韩立有什么神通" | "韩立眉头微皱..." | 0.35（中） | ❌ 低 |

### 解决方案

采用**混合检索**：语义相似度（60%）+ 词汇匹配（40%）

```
最终分数 = 0.6 × 语义相似度 + 0.4 × BM25归一化分数
```

### 文件改动

#### 新增文件

| 文件 | 说明 |
|------|------|
| `novel_system/semantic_scorer.py` | 语义相似度计算模块 |

#### 修改文件

| 文件 | 改动点 |
|------|--------|
| `novel_system/validator.py` | `EvidenceGate._compute_relevance()` 集成语义相似度 |
| `novel_system/indexing.py` | 索引时预计算 embedding |
| `novel_system/retrieval.py` | 检索结果携带 chunk_id |
| `requirements.txt` | 添加 `sentence-transformers` 依赖 |

### 核心代码

**1. semantic_scorer.py - 主要类和方法**

```python
class SemanticScorer:
    """语义相似度评分器"""

    SEMANTIC_WEIGHT = 0.6  # 语义相似度权重
    LEXICAL_WEIGHT = 0.4   # 词汇匹配权重

    def compute_embedding(self, text: str) -> np.ndarray:
        """计算文本嵌入向量"""

    def compute_similarity(self, query: str, text: str) -> float:
        """计算查询与文本的语义相似度"""

    def compute_similarity_with_hits(self, query: str, hits: list) -> float:
        """计算综合相似度（语义 + BM25）"""

def build_embedding_cache(chunks: list, output_path: Path):
    """构建 chunk 向量缓存（离线预计算）"""
```

**2. validator.py - 修改 EvidenceGate**

```python
class EvidenceGate:
    def __init__(self, use_semantic: bool = True):
        self.use_semantic = use_semantic
        if use_semantic:
            from .semantic_scorer import get_scorer
            self.semantic_scorer = get_scorer()

    def _compute_relevance(self, query: str, hits: list[Any]) -> float:
        if self.use_semantic and self.semantic_scorer:
            return self.semantic_scorer.compute_similarity_with_hits(query, hits)
        else:
            # 回退到纯 BM25
            return self._compute_lexical_relevance(hits)
```

**3. indexing.py - 预计算 embedding**

```python
def build_index(self, chunks: list[dict]):
    # ... 现有索引逻辑 ...

    # 预计算 embedding
    if self.config.enable_semantic:
        from .semantic_scorer import build_embedding_cache
        build_embedding_cache(
            chunks=chunks,
            output_path=self.index_dir / "embeddings.json",
        )
```

### 依赖添加

```txt
# requirements.txt
sentence-transformers>=2.2.0
numpy>=1.21.0
```

### 测试用例

```python
# tests/test_semantic_scorer.py

def test_semantic_similarity():
    """测试语义相似度计算"""
    scorer = SemanticScorer()

    # 同义表达应高分
    score1 = scorer.compute_similarity("主角的成名绝技", "韩立最擅长的神通是青元剑诀")
    assert score1 > 0.6

    # 无关内容应低分
    score2 = scorer.compute_similarity("主角的成名绝技", "今天天气不错")
    assert score2 < 0.4

def test_mixed_scoring():
    """测试混合评分"""
    scorer = SemanticScorer()

    hits = [MockHit(score=0.3, text="韩立施展青元剑诀击败敌人")]
    score = scorer.compute_similarity_with_hits("主角的成名绝技", hits)

    # 混合分数应高于纯 BM25
    assert score > 0.3

def test_embedding_cache():
    """测试向量缓存"""
    chunks = [
        {"id": "c1", "content": "韩立是本书的主角"},
        {"id": "c2", "content": "青元剑诀是一门强大的功法"},
    ]

    build_embedding_cache(chunks, Path("/tmp/test_embeddings.json"))

    scorer = SemanticScorer(cache_path=Path("/tmp/test_embeddings.json"))
    emb = scorer.get_cached_embedding("c1")
    assert emb is not None
    assert len(emb) == 384
```

---

## 优化二：AnswerValidator 幻觉检测

### 问题分析

**当前实现**：仅检查关键词覆盖率，无法检测"编造"的具体事实。

```python
# validator.py:276-297
def _compute_groundedness(self, answer: str, evidence: list[EvidenceItem]) -> float:
    answer_keywords = self._extract_keywords(answer)
    for kw in answer_keywords:
        if kw in evidence_text:
            covered += 1  # 关键词出现就算覆盖
```

**典型失败案例**：

```
证据：韩立性格谨慎，做事小心。
答案：韩立性格豪爽，喜欢与人结交朋友。
当前检测：通过（关键词"韩立"、"性格"都匹配）
实际：幻觉（性格描述完全相反）
```

### 解决方案

**三层验证机制**：

1. **关键词覆盖**（当前）- 快速过滤
2. **实体抽取 + 关系对比** - 检测事实冲突
3. **LLM 验证**（仅高风险）- 精确判断

```
验证流程：
答案 → 关键词覆盖检查 → (通过) → 实体关系对比 → (有冲突) → LLM 验证 → 最终判断
         ↓ (不通过)                  ↓ (无冲突)
       返回低分                    返回高分
```

### 文件改动

#### 修改文件

| 文件 | 改动点 |
|------|--------|
| `novel_system/validator.py` | 重构 `AnswerValidator` 类 |

#### 新增文件

| 文件 | 说明 |
|------|------|
| `novel_system/entity_extractor.py` | 实体抽取模块 |

### 核心代码

**1. entity_extractor.py - 实体抽取**

```python
"""
实体抽取模块

从文本中抽取人名、属性、关系等结构化信息
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Entity:
    """实体"""
    name: str
    entity_type: str  # person, item, location, ability
    attributes: dict[str, str]  # 属性键值对


@dataclass
class Relation:
    """关系"""
    subject: str
    predicate: str  # 是, 有, 属于, 使用
    obj: str


class EntityExtractor:
    """
    实体抽取器

    使用规则 + 模式匹配抽取实体和关系
    """

    # 人名模式
    PERSON_PATTERNS = [
        r'([\u4e00-\u9fa5]{2,4})(?=说道|道:|笑道|皱眉|点头|摇头)',
        r'(韩立|南宫婉|厉飞雨|墨居仁|李化元)',  # 已知人名
    ]

    # 属性模式
    ATTRIBUTE_PATTERNS = {
        "性格": r'(性格|性情|为人)(是|为|比较)([\u4e00-\u9fa5]{2,6})',
        "外貌": r'(相貌|面容|长相)(是|为|比较)?([\u4e00-\u9fa5]{2,10})',
        "能力": r'(修炼|擅长|精通)([\u4e00-\u9fa5]{2,8})',
    }

    # 颜色对立关系
    COLOR_OPPOSITES = {
        "黑": ["白", "金"],
        "白": ["黑", "灰"],
        "金": ["黑"],
        "红": ["青", "蓝"],
    }

    # 性格对立关系
    PERSONALITY_OPPOSITES = {
        "谨慎": ["豪爽", "冲动", "鲁莽"],
        "豪爽": ["谨慎", "小心", "拘谨"],
        "冷漠": ["热情", "热心"],
        "热情": ["冷漠", "冷淡"],
    }

    def extract_entities(self, text: str) -> list[Entity]:
        """从文本中抽取实体"""
        entities = []

        # 抽取人名
        for pattern in self.PERSON_PATTERNS:
            matches = re.findall(pattern, text)
            for match in matches:
                name = match if isinstance(match, str) else match[0]
                entities.append(Entity(name=name, entity_type="person", attributes={}))

        return entities

    def extract_attributes(self, text: str, entity_name: str) -> dict[str, str]:
        """抽取实体的属性"""
        attributes = {}

        for attr_type, pattern in self.ATTRIBUTE_PATTERNS.items():
            # 查找实体相关的属性描述
            context_pattern = f'{entity_name}[^。！？]{{0,20}}{pattern}'
            match = re.search(context_pattern, text)
            if match:
                attributes[attr_type] = match.group(3)

        return attributes

    def extract_relations(self, text: str) -> list[Relation]:
        """抽取实体间关系"""
        relations = []

        # 简单的关系模式
        relation_patterns = [
            r'([\u4e00-\u9fa5]{2,4})的([\u4e00-\u9fa5]{2,6})是([\u4e00-\u9fa5]{2,8})',
        ]

        for pattern in relation_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                relations.append(Relation(
                    subject=match[0],
                    predicate=f"{match[1]}是",
                    obj=match[2],
                ))

        return relations

    def check_contradiction(
        self,
        attr_type: str,
        value1: str,
        value2: str,
    ) -> bool:
        """
        检查两个属性值是否矛盾

        Args:
            attr_type: 属性类型 (性格, 外貌, etc.)
            value1: 第一个值
            value2: 第二个值

        Returns:
            是否矛盾
        """
        # 检查颜色对立
        if attr_type == "外貌":
            for color, opposites in self.COLOR_OPPOSITES.items():
                if color in value1 and any(opp in value2 for opp in opposites):
                    return True

        # 检查性格对立
        if attr_type == "性格":
            for personality, opposites in self.PERSONALITY_OPPOSITES.items():
                if personality in value1 and any(opp in value2 for opp in opposites):
                    return True
                if personality in value2 and any(opp in value1 for opp in opposites):
                    return True

        return False
```

**2. validator.py - 重构 AnswerValidator**

```python
class AnswerValidator:
    """答案验证器"""

    def __init__(self, use_llm_verification: bool = False):
        self.use_llm_verification = use_llm_verification
        self.entity_extractor = EntityExtractor()

    def validate(
        self,
        query: str,
        answer: str,
        evidence: list[EvidenceItem],
        gate_result: EvidenceGateResult,
    ) -> AnswerValidationResult:
        """验证答案质量"""

        # 1. 关键词覆盖检查（快速）
        keyword_score = self._compute_groundedness(answer, evidence)

        # 2. 实体关系对比（中等精度）
        entity_issues = self._check_entity_consistency(answer, evidence)

        # 3. 综合评估
        hallucination_risk = self._assess_hallucination_risk(
            keyword_score, entity_issues, gate_result
        )

        # 4. 高风险时启用 LLM 验证
        if self.use_llm_verification and hallucination_risk == "high":
            llm_result = self._llm_verify(answer, evidence)
            if llm_result.get("has_hallucination"):
                entity_issues.append(llm_result.get("reason", "LLM 检测到幻觉"))

        return AnswerValidationResult(
            valid=len(entity_issues) == 0,
            groundedness_score=keyword_score,
            hallucination_risk=hallucination_risk,
            confidence=self._compute_confidence(gate_result, keyword_score, hallucination_risk),
            issues=entity_issues,
            suggestions=self._generate_suggestions(entity_issues),
        )

    def _check_entity_consistency(
        self,
        answer: str,
        evidence: list[EvidenceItem],
    ) -> list[str]:
        """检查实体一致性"""
        issues = []

        # 从证据中抽取实体和属性
        evidence_entities = {}
        for e in evidence:
            entities = self.entity_extractor.extract_entities(e.quote)
            for entity in entities:
                attrs = self.entity_extractor.extract_attributes(e.quote, entity.name)
                if entity.name not in evidence_entities:
                    evidence_entities[entity.name] = {}
                evidence_entities[entity.name].update(attrs)

        # 从答案中抽取实体和属性
        answer_entities = {}
        entities = self.entity_extractor.extract_entities(answer)
        for entity in entities:
            attrs = self.entity_extractor.extract_attributes(answer, entity.name)
            answer_entities[entity.name] = attrs

        # 对比检查矛盾
        for name, answer_attrs in answer_entities.items():
            if name not in evidence_entities:
                issues.append(f"答案提及的 '{name}' 未在证据中出现")
                continue

            for attr_type, answer_value in answer_attrs.items():
                evidence_value = evidence_entities[name].get(attr_type)
                if evidence_value:
                    if self.entity_extractor.check_contradiction(
                        attr_type, evidence_value, answer_value
                    ):
                        issues.append(
                            f"'{name}' 的{attr_type}描述矛盾："
                            f"证据为 '{evidence_value}'，答案为 '{answer_value}'"
                        )

        return issues

    def _llm_verify(self, answer: str, evidence: list[EvidenceItem]) -> dict:
        """使用 LLM 验证答案"""
        # 调用 LLM 进行验证
        evidence_text = "\n".join([e.quote for e in evidence if e.quote])

        prompt = f"""请判断以下答案是否完全由给定证据支持。

证据：
{evidence_text}

答案：
{answer}

请回答：
1. 答案是否有幻觉（编造了证据中没有的内容）？YES/NO
2. 如果有幻觉，请说明具体是哪部分。

请用 JSON 格式回答：
{{"has_hallucination": false/true, "reason": "说明"}}"""

        # 调用 LLM（伪代码，需要实际实现）
        # response = call_llm(prompt)
        # return parse_json(response)

        return {"has_hallucination": False, "reason": ""}  # 默认返回
```

### 测试用例

```python
# tests/test_entity_extractor.py

def test_extract_person_name():
    """测试人名抽取"""
    extractor = EntityExtractor()
    text = "韩立皱眉道：此事有些蹊跷。"
    entities = extractor.extract_entities(text)
    assert any(e.name == "韩立" for e in entities)

def test_extract_attributes():
    """测试属性抽取"""
    extractor = EntityExtractor()
    text = "韩立性格谨慎，做事小心。"
    attrs = extractor.extract_attributes(text, "韩立")
    assert "性格" in attrs
    assert "谨慎" in attrs["性格"]

def test_contradiction_detection():
    """测试矛盾检测"""
    extractor = EntityExtractor()

    # 性格矛盾
    assert extractor.check_contradiction("性格", "谨慎", "豪爽") == True
    assert extractor.check_contradiction("性格", "谨慎", "小心") == False

    # 颜色矛盾
    assert extractor.check_contradiction("外貌", "黑发", "金发") == True
    assert extractor.check_contradiction("外貌", "黑发", "长发") == False

def test_answer_validation_with_contradiction():
    """测试答案验证（有矛盾）"""
    validator = AnswerValidator()

    evidence = [EvidenceItem(quote="韩立性格谨慎，做事小心。", source="test")]
    answer = "韩立性格豪爽，喜欢与人结交。"

    result = validator.validate(
        query="韩立是什么性格？",
        answer=answer,
        evidence=evidence,
        gate_result=EvidenceGateResult(sufficient=True, relevance_score=0.8),
    )

    assert result.hallucination_risk in ["medium", "high"]
    assert any("矛盾" in issue for issue in result.issues)
```

---

## 优化三：SpoilerGuard 精准度

### 问题分析

**当前实现**：基于关键词匹配，误报率较高。

```python
# validator.py:599-620
FUTURE_KEYWORDS = ["最终", "结局", "后来", "以后", "最后", "成功"]
PLOT_TWIST_KEYWORDS = ["背叛", "死亡", "牺牲", "觉醒", "突破"]
```

**典型误报案例**：

```
内容："韩立成功炼制了一颗丹药。"
检测：触发 "成功" → 判定为剧透
实际：普通情节，非剧透
```

**典型漏报案例**：

```
内容："掌天瓶的秘密是..."
检测：未触发关键词
实际：涉及核心设定剧透
```

### 解决方案

**三层检测机制**：

1. **白名单过滤** - 排除明显的非剧透语境
2. **上下文窗口** - 结合前后文判断
3. **事件类型分类** - 区分普通情节和关键剧情

```
检测流程：
内容 → 白名单过滤 → 上下文分析 → 事件分类 → 最终判断
         ↓               ↓            ↓
      排除非剧透     识别语境     区分严重程度
```

### 文件改动

#### 修改文件

| 文件 | 改动点 |
|------|--------|
| `novel_system/validator.py` | 重构 `SpoilerGuard` 类 |

### 核心代码

```python
class SpoilerGuard:
    """剧透防护"""

    # 未来事件关键词
    FUTURE_KEYWORDS = [
        "最终", "结局", "后来", "以后", "最后",
        "真相", "原来", "到底", "终于",
    ]

    # 关键剧情关键词
    PLOT_TWIST_KEYWORDS = [
        "背叛", "死亡", "牺牲", "觉醒", "突破",
        "获得", "发现", "揭示", "秘密",
    ]

    # 白名单：这些语境下的关键词不算剧透
    SPOILER_WHITELIST = {
        "成功": [
            "成功炼制", "成功制作", "成功完成",
            "成功击败", "成功逃脱", "成功获得",
        ],
        "突破": [
            "突破瓶颈",  # 普通修炼，非剧透
        ],
        "发现": [
            "发现一个", "发现这里", "发现眼前",  # 普通发现
        ],
        "秘密": [
            "秘密通道", "秘密基地",  # 普通秘密
        ],
    }

    # 剧透语境模式：这些语境更可能是剧透
    SPOILER_CONTEXTS = [
        r'最终(成为|达到|获得)',  # 最终结果
        r'后来(才知道|才发现)',   # 后续揭示
        r'原来是',                # 真相揭示
        r'真正的(身份|实力)',      # 身份揭示
        r'(背叛|出卖).{0,10}(了|的)',  # 背叛情节
    ]

    # 普通情节模式：这些不算剧透
    NORMAL_CONTEXTS = [
        r'成功(炼制|制作|完成).{0,5}(丹药|法宝|任务)',  # 普通成功
        r'突破.{0,3}瓶颈',  # 普通突破
    ]

    def detect_spoiler(
        self,
        content: str,
        scope: Scope,
        total_chapters: int,
        event_timeline: list[dict[str, Any]],
    ) -> SpoilerRisk:
        """检测剧透内容"""

        if not scope.chapters:
            return SpoilerRisk(level="none")

        max_read_chapter = max(scope.chapters)

        # 1. 白名单过滤
        filtered_content = self._apply_whitelist(content)

        # 2. 上下文分析
        context_spoilers = self._analyze_context(filtered_content, max_read_chapter)

        # 3. 事件时间线匹配
        event_spoilers = self._detect_event_spoilers(
            content, event_timeline, max_read_chapter
        )

        # 4. 综合评估
        risk_level = self._assess_risk_level(
            context_spoilers, event_spoilers, max_read_chapter, total_chapters
        )

        return SpoilerRisk(
            level=risk_level,
            spoiler_content=context_spoilers + [e.get('title', '') for e in event_spoilers],
            affected_chapters=[e.get('chapter', 0) for e in event_spoilers],
            suggestions=self._generate_suggestions(risk_level),
        )

    def _apply_whitelist(self, content: str) -> str:
        """应用白名单，标记非剧透内容"""
        marked_content = content

        for keyword, whitelist_patterns in self.SPOILER_WHITELIST.items():
            for pattern in whitelist_patterns:
                # 将白名单匹配的内容替换为占位符
                marked_content = marked_content.replace(
                    pattern,
                    f"[[NORMAL:{pattern}]]"
                )

        return marked_content

    def _analyze_context(self, content: str, max_read_chapter: int) -> list[str]:
        """分析上下文，识别剧透语境"""

        spoilers = []

        # 检查剧透语境模式
        for pattern in self.SPOILER_CONTEXTS:
            matches = re.findall(pattern, content)
            for match in matches:
                # 排除白名单标记的内容
                context = self._get_context(content, match, window=20)
                if "[[NORMAL:" not in context:
                    spoilers.append(f"疑似剧透语境: '{match}'")

        # 检查普通语境模式（排除）
        for pattern in self.NORMAL_CONTEXTS:
            matches = re.findall(pattern, content)
            for match in matches:
                # 标记为普通情节
                pass  # 这些不是剧透

        return spoilers

    def _get_context(self, text: str, keyword: str, window: int = 20) -> str:
        """获取关键词的上下文"""
        idx = text.find(keyword)
        if idx == -1:
            return ""
        start = max(0, idx - window)
        end = min(len(text), idx + len(keyword) + window)
        return text[start:end]

    def _assess_risk_level(
        self,
        context_spoilers: list[str],
        event_spoilers: list[dict],
        max_read_chapter: int,
        total_chapters: int,
    ) -> Literal["none", "low", "medium", "high"]:
        """评估风险级别"""

        # 高风险：明确提及未来章节的关键事件
        if event_spoilers:
            # 判断事件是否在较远的未来
            for event in event_spoilers:
                event_chapter = event.get('chapter', 0)
                if event_chapter > max_read_chapter + 50:  # 远超当前进度
                    return "high"
            return "medium"

        # 中风险：多个剧透语境
        if len(context_spoilers) >= 2:
            return "medium"

        # 低风险：单个剧透语境
        if context_spoilers:
            return "low"

        return "none"

    def redact_content(
        self,
        content: str,
        spoiler_risk: SpoilerRisk,
    ) -> str:
        """消除剧透内容"""

        if spoiler_risk.level == "none":
            return content

        # 移除白名单标记
        result = re.sub(r'\[\[NORMAL:([^\]]+)\]\]', r'\1', content)

        if spoiler_risk.level == "high":
            return "【内容涉及后续情节，为避免剧透已隐藏】"

        if spoiler_risk.level == "medium":
            return f"【⚠️ 可能包含剧透】{result}"

        return result
```

### 测试用例

```python
# tests/test_spoiler_guard.py

def test_whitelist_normal_content():
    """测试白名单过滤普通内容"""
    guard = SpoilerGuard()
    scope = Scope(chapters=[1, 2, 3])

    # 普通成功事件不应误判
    result = guard.detect_spoiler(
        content="韩立成功炼制了一颗丹药。",
        scope=scope,
        total_chapters=100,
        event_timeline=[],
    )
    assert result.level == "none"

def test_detect_real_spoiler():
    """测试检测真实剧透"""
    guard = SpoilerGuard()
    scope = Scope(chapters=[1, 2, 3])

    # 真正的剧透应被检测
    result = guard.detect_spoiler(
        content="韩立最终成为了仙界的至强者。",
        scope=scope,
        total_chapters=100,
        event_timeline=[],
    )
    assert result.level in ["medium", "high"]

def test_context_analysis():
    """测试上下文分析"""
    guard = SpoilerGuard()

    # "原来"在揭示真相语境下是剧透
    context1 = guard._analyze_context("原来韩立的真实身份是天帝转世", 10)
    assert len(context1) > 0

    # "原来"在普通语境下不是剧透
    marked = guard._apply_whitelist("韩立原来就有这个法宝")
    context2 = guard._analyze_context(marked, 10)
    # 应该被白名单过滤或上下文判断为非剧透

def test_event_timeline_spoiler():
    """测试事件时间线检测"""
    guard = SpoilerGuard()
    scope = Scope(chapters=[1, 2, 3])

    timeline = [
        {"chapter": 10, "title": "韩立突破筑基期"},
        {"chapter": 50, "title": "韩立成为元婴修士"},
    ]

    result = guard.detect_spoiler(
        content="韩立成为了元婴修士。",
        scope=scope,
        total_chapters=100,
        event_timeline=timeline,
    )
    assert result.level == "high"
    assert 50 in result.affected_chapters
```

---

## 优化四：ContinuationValidator 增强

### 问题分析

**当前实现**：只检测外貌颜色，遗漏大量一致性问题。

```python
# validator.py:472-498
def _extract_appearance_keywords(self, appearance: str) -> list[str]:
    colors = re.findall(r'(黑|白|金|红|青|蓝|绿|黄|紫|灰|褐)[发须眉眼瞳肤]', appearance)
    # 只提取颜色，遗漏其他特征
```

**典型遗漏案例**：

```
人物卡：韩立 - 相貌平平，皮肤黝黑，眼神灵动，性格谨慎
续写：韩立面容英俊，举止豪迈，说话大声
当前检测：只检测到颜色 → 遗漏多个不一致
应检测：
  - "相貌平平" vs "面容英俊" → 外貌矛盾
  - "性格谨慎" vs "举止豪迈" → 性格矛盾
```

### 解决方案

**扩展检测维度**：

| 维度 | 检测内容 | 方法 |
|------|---------|------|
| 外貌 | 体型、五官、肤色 | 关键词 + 对立词库 |
| 性格 | 性格特征 | 性格词库 + 对立关系 |
| 能力 | 修为等级、神通 | 等级体系 + 能力列表 |
| 关系 | 人物关系 | 关系图谱 |

### 文件改动

#### 修改文件

| 文件 | 改动点 |
|------|--------|
| `novel_system/validator.py` | 重构 `ContinuationValidator` 类 |

### 核心代码

```python
class ContinuationValidator:
    """续写验证器"""

    # 体型关键词
    BODY_TYPE_KEYWORDS = {
        "高": ["高大", "修长", "挺拔"],
        "矮": ["矮小", "瘦小"],
        "胖": ["肥胖", "壮硕", "魁梧"],
        "瘦": ["消瘦", "瘦弱", "纤细"],
    }

    # 五官特征关键词
    FACIAL_FEATURES = {
        "英俊": ["俊朗", "英俊", "帅气", "俊美"],
        "普通": ["相貌平平", "相貌普通", "长相一般", "容貌平常"],
        "丑陋": ["丑陋", "难看", "面目可憎"],
    }

    # 性格特征及其对立
    PERSONALITY_TRAITS = {
        "谨慎": {
            "synonyms": ["小心", "慎重", "稳重", "小心翼翼"],
            "opposites": ["豪爽", "冲动", "鲁莽", "冒失"],
        },
        "豪爽": {
            "synonyms": ["豪迈", "洒脱", "大方"],
            "opposites": ["谨慎", "拘谨", "小气"],
        },
        "冷漠": {
            "synonyms": ["冷淡", "冷峻", "冷漠"],
            "opposites": ["热情", "热心", "温和"],
        },
        "狡猾": {
            "synonyms": ["狡诈", "阴险", "城府深"],
            "opposites": ["正直", "老实", "淳朴"],
        },
    }

    # 修为等级体系
    CULTIVATION_LEVELS = [
        "炼气期", "筑基期", "结丹期", "元婴期", "化神期",
        "炼虚期", "合体期", "大乘期", "渡劫期", "仙人",
    ]

    def validate(
        self,
        continuation: str,
        character_cards: list[dict[str, Any]],
        world_rules: list[dict[str, Any]],
        style_samples: list[str],
        scope: Scope,
    ) -> ContinuationValidationResult:
        """验证续写内容"""

        # 1. 人物一致性检查
        character_issues = self.check_character_consistency(
            continuation, character_cards, scope
        )

        # 2. 世界边界检查
        world_issues = self.check_world_boundary(
            continuation, world_rules, scope
        )

        # 3. 文风一致性检查
        style_issues = self.check_style_consistency(
            continuation, style_samples
        )

        # 4. 计算总分
        total_issues = len(character_issues) + len(world_issues) + len(style_issues)
        overall_score = max(0.0, 1.0 - total_issues * 0.12)

        return ContinuationValidationResult(
            valid=overall_score >= 0.6,
            character_issues=character_issues,
            world_issues=world_issues,
            style_issues=style_issues,
            overall_score=overall_score,
            details=self._generate_details(character_issues, world_issues, style_issues),
        )

    def check_character_consistency(
        self,
        continuation: str,
        character_cards: list[dict[str, Any]],
        scope: Scope,
    ) -> list[str]:
        """检查人物一致性"""

        issues = []

        for card in character_cards:
            name = card.get("name", "")
            if name not in continuation:
                continue

            # 检查外貌一致性
            appearance_issues = self._check_appearance(
                continuation, name, card.get("appearance", "")
            )
            issues.extend(appearance_issues)

            # 检查性格一致性
            personality_issues = self._check_personality(
                continuation, name, card.get("personality", "")
            )
            issues.extend(personality_issues)

            # 检查能力一致性
            ability_issues = self._check_abilities(
                continuation, name, card.get("abilities", []), scope
            )
            issues.extend(ability_issues)

            # 检查修为等级一致性
            level_issues = self._check_cultivation_level(
                continuation, name, card.get("level", ""), scope
            )
            issues.extend(level_issues)

        return issues

    def _check_appearance(
        self,
        continuation: str,
        name: str,
        appearance: str,
    ) -> list[str]:
        """检查外貌一致性"""
        issues = []

        if not appearance:
            return issues

        # 检查体型
        for body_type, keywords in self.BODY_TYPE_KEYWORDS.items():
            if any(kw in appearance for kw in keywords):
                # 检查续写中是否有对立描述
                for other_type, other_keywords in self.BODY_TYPE_KEYWORDS.items():
                    if other_type != body_type:
                        for kw in other_keywords:
                            pattern = f"{name}.{{0,20}}{kw}"
                            if re.search(pattern, continuation):
                                issues.append(
                                    f"'{name}' 的体型描述矛盾："
                                    f"原文为 '{body_type}' 类型，续写中出现 '{kw}'"
                                )

        # 检查五官特征
        for feature_type, keywords in self.FACIAL_FEATURES.items():
            if any(kw in appearance for kw in keywords):
                for other_feature, other_keywords in self.FACIAL_FEATURES.items():
                    if other_feature != feature_type:
                        for kw in other_keywords:
                            pattern = f"{name}.{{0,20}}{kw}"
                            if re.search(pattern, continuation):
                                issues.append(
                                    f"'{name}' 的面容描述矛盾："
                                    f"原文为 '{feature_type}'，续写中出现 '{kw}'"
                                )

        # 检查颜色特征（保留原有逻辑）
        color_issues = self._check_color_consistency(continuation, name, appearance)
        issues.extend(color_issues)

        return issues

    def _check_color_consistency(
        self,
        continuation: str,
        name: str,
        appearance: str,
    ) -> list[str]:
        """检查颜色一致性"""
        issues = []

        color_opposites = {
            "黑": ["白", "金"],
            "白": ["黑", "灰"],
            "金": ["黑"],
        }

        for color, opposites in color_opposites.items():
            if color in appearance and any(
                f"{color}{part}" in appearance
                for part in ["发", "须", "眉", "眼", "瞳"]
            ):
                for opposite in opposites:
                    pattern = f"{name}.{{0,30}}{opposite}[发须眉眼瞳]"
                    if re.search(pattern, continuation):
                        issues.append(
                            f"'{name}' 的颜色特征矛盾："
                            f"原文为 '{color}'，续写中出现 '{opposite}'"
                        )

        return issues

    def _check_personality(
        self,
        continuation: str,
        name: str,
        personality: str,
    ) -> list[str]:
        """检查性格一致性"""
        issues = []

        if not personality:
            return issues

        # 查找人物的性格特征
        for trait, info in self.PERSONALITY_TRAITS.items():
            if trait in personality or any(syn in personality for syn in info["synonyms"]):
                # 检查续写中是否有对立性格
                for opposite in info["opposites"]:
                    # 查找人物相关的性格描述
                    pattern = f"{name}.{{0,50}}{opposite}"
                    if re.search(pattern, continuation):
                        issues.append(
                            f"'{name}' 的性格描述矛盾："
                            f"原文性格为 '{trait}'，续写中出现 '{opposite}'"
                        )

        return issues

    def _check_abilities(
        self,
        continuation: str,
        name: str,
        abilities: list[str],
        scope: Scope,
    ) -> list[str]:
        """检查能力一致性"""
        issues = []

        if not abilities:
            return issues

        max_chapter = max(scope.chapters) if scope.chapters else 0

        for ability in abilities:
            # 检查续写是否使用了超出范围的能力
            if ability in continuation:
                # 简单检查：能力是否在合理范围内
                pass  # 需要更多信息来判断

        return issues

    def _check_cultivation_level(
        self,
        continuation: str,
        name: str,
        level: str,
        scope: Scope,
    ) -> list[str]:
        """检查修为等级一致性"""
        issues = []

        if not level:
            return issues

        # 获取人物当前等级索引
        current_level_idx = -1
        for i, lvl in enumerate(self.CULTIVATION_LEVELS):
            if lvl in level:
                current_level_idx = i
                break

        if current_level_idx == -1:
            return issues

        # 检查续写中的等级是否合理
        for i, lvl in enumerate(self.CULTIVATION_LEVELS):
            if lvl in continuation:
                if i > current_level_idx + 1:
                    # 跳级太多，可能有问题
                    issues.append(
                        f"'{name}' 的修为等级跳跃过大："
                        f"原文为 '{level}'，续写中提及 '{lvl}'"
                    )

        return issues

    def check_world_boundary(
        self,
        continuation: str,
        world_rules: list[dict[str, Any]],
        scope: Scope,
    ) -> list[str]:
        """检查世界边界"""
        issues = []

        for rule in world_rules:
            rule_text = rule.get("text", "") or rule.get("rule", "")
            if not rule_text:
                continue

            # 检查禁止规则
            if any(kw in rule_text for kw in ["不能", "禁止", "不可能", "无法"]):
                # 提取规则中的关键实体
                entities = re.findall(r'[\u4e00-\u9fa5]{2,4}', rule_text)

                for entity in entities:
                    # 检查续写是否违反规则
                    if entity in continuation:
                        # 简单判断：如果规则说"不能X"，而续写出现了"X成功"
                        if "成功" in continuation:
                            issues.append(
                                f"续写可能违反规则：'{rule_text[:50]}...'"
                            )
                            break

        return issues

    def check_style_consistency(
        self,
        continuation: str,
        style_samples: list[str],
    ) -> list[str]:
        """检查文风一致性"""
        issues = []

        if not style_samples:
            return issues

        # 分析原文风格
        sample_styles = [self._analyze_style(sample) for sample in style_samples if sample]
        if not sample_styles:
            return issues

        avg_sentence_length = sum(
            s.get("avg_sentence_length", 0) for s in sample_styles
        ) / len(sample_styles)

        # 分析续写风格
        cont_style = self._analyze_style(continuation)
        cont_sentence_length = cont_style.get("avg_sentence_length", 0)

        # 检查句子长度差异
        if avg_sentence_length > 0:
            diff_ratio = abs(cont_sentence_length - avg_sentence_length) / avg_sentence_length
            if diff_ratio > 0.5:
                issues.append(
                    f"句子长度风格差异较大："
                    f"原文平均 {avg_sentence_length:.1f} 字，"
                    f"续写平均 {cont_sentence_length:.1f} 字"
                )

        # 检查对话风格
        dialogue_issues = self._check_dialogue_style(continuation, style_samples)
        issues.extend(dialogue_issues)

        return issues

    def _check_dialogue_style(
        self,
        continuation: str,
        style_samples: list[str],
    ) -> list[str]:
        """检查对话风格"""
        issues = []

        # 统计对话标记
        continuation_dialogues = len(re.findall(r'[""「」『』]', continuation))

        sample_dialogues = sum(
            len(re.findall(r'[""「」『』]', sample))
            for sample in style_samples
        ) / len(style_samples) if style_samples else 0

        # 如果对话密度差异过大
        if sample_dialogues > 0:
            cont_len = len(continuation)
            sample_avg_len = sum(len(s) for s in style_samples) / len(style_samples)

            cont_dialogue_density = continuation_dialogues / cont_len if cont_len > 0 else 0
            sample_dialogue_density = sample_dialogues / sample_avg_len if sample_avg_len > 0 else 0

            if abs(cont_dialogue_density - sample_dialogue_density) > 0.01:
                issues.append("对话密度与原文风格差异较大")

        return issues

    def _analyze_style(self, text: str) -> dict[str, Any]:
        """分析文本风格"""
        sentences = re.split(r'[。！？]', text)
        sentences = [s for s in sentences if s.strip()]

        avg_length = sum(len(s) for s in sentences) / len(sentences) if sentences else 0

        return {
            "avg_sentence_length": avg_length,
            "sentence_count": len(sentences),
        }
```

### 测试用例

```python
# tests/test_continuation_validator.py

def test_check_appearance_contradiction():
    """测试外貌矛盾检测"""
    validator = ContinuationValidator()

    continuation = "韩立面容英俊，身材高大，声音洪亮。"
    character_cards = [{
        "name": "韩立",
        "appearance": "相貌平平，皮肤黝黑，身材普通",
        "personality": "",
    }]

    issues = validator.check_character_consistency(
        continuation, character_cards, Scope(chapters=[1, 2, 3])
    )

    assert any("面容" in issue or "英俊" in issue for issue in issues)

def test_check_personality_contradiction():
    """测试性格矛盾检测"""
    validator = ContinuationValidator()

    continuation = "韩立哈哈大笑，说道：这种小事，何必放在心上！"
    character_cards = [{
        "name": "韩立",
        "appearance": "",
        "personality": "性格谨慎，做事小心，不轻易表态",
    }]

    issues = validator.check_character_consistency(
        continuation, character_cards, Scope(chapters=[1, 2, 3])
    )

    assert any("性格" in issue for issue in issues)

def test_check_cultivation_level_jump():
    """测试修为等级跳跃检测"""
    validator = ContinuationValidator()

    continuation = "韩立已是化神期高手，一掌拍出，天地变色。"
    character_cards = [{
        "name": "韩立",
        "appearance": "",
        "personality": "",
        "level": "炼气期三层",
    }]

    issues = validator.check_character_consistency(
        continuation, character_cards, Scope(chapters=[1, 2, 3])
    )

    assert any("修为" in issue or "等级" in issue for issue in issues)

def test_check_style_consistency():
    """测试文风一致性检测"""
    validator = ContinuationValidator()

    # 原文：短句为主
    style_samples = [
        "韩立皱眉。他心中一动。这有问题。",
        "此人不简单。需小心应对。韩立暗想。",
    ]

    # 续写：长句为主
    continuation = (
        "韩立眉头微微皱起，心中暗自思索着这件事情的来龙去脉，"
        "总觉得其中似乎隐藏着什么不可告人的秘密，必须小心谨慎地应对才行。"
    )

    issues = validator.check_style_consistency(continuation, style_samples)

    assert any("风格" in issue or "句子" in issue for issue in issues)
```

---

## 实施计划

### 阶段划分

| 阶段 | 优化项 | 预计工作量 | 优先级 |
|------|--------|-----------|--------|
| **第一阶段** | SpoilerGuard 精准度 | 1-2 天 | P0 |
| **第二阶段** | EvidenceGate 语义相似度 | 2-3 天 | P0 |
| **第三阶段** | ContinuationValidator 增强 | 2-3 天 | P1 |
| **第四阶段** | AnswerValidator 幻觉检测 | 2-3 天 | P2 |

### 依赖关系

```
第一阶段（无依赖）
    └── SpoilerGuard 精准度

第二阶段（无依赖）
    └── EvidenceGate 语义相似度
        └── 需要：sentence-transformers 库

第三阶段（依赖第二阶段的 EntityExtractor）
    └── ContinuationValidator 增强
        └── 复用：EntityExtractor

第四阶段（依赖第二阶段的 EntityExtractor）
    └── AnswerValidator 幻觉检测
        └── 复用：EntityExtractor
        └── 可选：LLM 验证
```

### 文件清单

#### 新增文件

| 文件 | 阶段 | 说明 |
|------|------|------|
| `novel_system/semantic_scorer.py` | 二 | 语义相似度计算 |
| `novel_system/entity_extractor.py` | 二 | 实体抽取模块 |
| `tests/test_semantic_scorer.py` | 二 | 语义相似度测试 |
| `tests/test_entity_extractor.py` | 二 | 实体抽取测试 |
| `tests/test_spoiler_guard.py` | 一 | 剧透防护测试 |
| `tests/test_continuation_validator.py` | 三 | 续写验证测试 |

#### 修改文件

| 文件 | 阶段 | 改动点 |
|------|------|--------|
| `novel_system/validator.py` | 一、三、四 | 四个验证器类 |
| `novel_system/indexing.py` | 二 | 预计算 embedding |
| `novel_system/retrieval.py` | 二 | 携带 chunk_id |
| `requirements.txt` | 二 | 添加依赖 |

---

## 附录：性能考量

### 延迟影响

| 优化项 | 增量延迟 | 优化方案 |
|--------|---------|---------|
| EvidenceGate 语义相似度 | +15-30ms | 预计算 embedding |
| AnswerValidator LLM 验证 | +500-2000ms | 仅高风险启用 |
| SpoilerGuard 上下文分析 | +5-10ms | 正则优化 |
| ContinuationValidator 增强 | +10-20ms | 提前过滤不相关人物 |

### 内存占用

| 组件 | 内存占用 | 说明 |
|------|---------|------|
| Embedding 模型 | ~420MB | 可按需加载 |
| Embedding 缓存 | ~4MB/万chunk | 可配置是否启用 |
| 实体抽取器 | ~1MB | 规则 + 词库 |

---

## 总结

本文档详细说明了四个优化方向的实现方案：

1. **EvidenceGate 语义相似度**：引入 embedding 模型，提升相关性判断准确率
2. **AnswerValidator 幻觉检测**：实体抽取 + 关系对比 + 可选 LLM 验证
3. **SpoilerGuard 精准度**：白名单 + 上下文分析 + 事件分类
4. **ContinuationValidator 增强**：扩展外貌、性格、能力、修为等级检测

建议按优先级顺序实施，每个阶段完成后进行测试验证。
