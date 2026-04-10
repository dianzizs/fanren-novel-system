# 《凡人修仙传》小说拆书 / 问答 / 续写系统自动评测集（v1）

这套评测集是基于你的系统设计文档整理的，目标不是只测“答对没”，而是同时测：

1. **Planner 是否选对任务类型**
2. **Retrieval 是否检索了正确的信息层**
3. **QA 是否 grounded**
4. **Continuation 是否遵守设定与边界**
5. **Memory 是否记住用户偏好与范围**
6. **Safety / Governance 是否可靠**
7. **Harness / Fallback 是否具备恢复能力**

---

## 文件说明

- `fanren_eval_cases_v1.jsonl`
  - 主测试集
  - 每行一个 case
  - 适合直接喂给评测脚本

- `fanren_eval_runner_template.py`
  - 一个可运行的评测脚本模板
  - 输入：`cases.jsonl` + `predictions.jsonl`
  - 输出：总分、分类型得分、失败用例

- `fanren_eval_readme.md`
  - 当前这份说明文档

---

## 建议的被测系统输出格式

为了更稳定地自动评估，建议你的系统对每个请求输出如下 JSON：

```json
{
  "id": "qa_001",
  "planner": {
    "task_type": "qa",
    "retrieval_needed": true,
    "retrieval_targets": ["chapter_chunks", "event_timeline"],
    "constraints": ["grounded_answer", "cite_evidence"],
    "success_criteria": ["answer_correct", "no_spoiler"]
  },
  "answer": "……",
  "evidence": [
    {"chapter": 1, "quote": "……"}
  ],
  "uncertainty": "low"
}
```

如果你的系统当前还没有输出结构化 planner，也没关系。  
模板脚本会优先评估 `answer` 文本；如果带了 `planner`，会再加一层评测。

---

## case 字段说明

每条 case 主要包含：

- `id`：唯一标识
- `priority`：P0 / P1
- `category`：类别
- `input`：用户请求、范围、上下文
- `expected_result`：预期结果
- `scoring`：建议打分方法

---

## 类别设计

### 1. QA Grounded
适合测：
- 单跳事实问答
- 跨章节事实问答
- 角色比较
- 事件原因 / 结果

自动评测重点：
- 是否命中核心事实
- 是否避开错误断言
- 是否超出当前范围乱剧透

### 2. Summary / Extraction
适合测：
- 章节摘要
- 时间线
- 人物卡
- 势力关系

自动评测重点：
- 是否覆盖关键事件
- 顺序是否基本正确
- 是否把后文知识提前带入

### 3. Planner / Retrieval
适合测：
- task_type 是否合理
- retrieval_needed 是否合理
- retrieval_targets 是否匹配任务

自动评测重点：
- 问答不能用 continuation 的策略
- 续写不能只检索相似段落，必须拉 recent_plot + canon_memory + style_samples
- 结构化抽取不能只拿一段 chunk

### 4. Continuation Constraint
适合测：
- 人设一致性
- 世界边界
- 不剧透
- 不胡跳战力

自动评测重点：
- required_points 命中率
- forbidden_points 违规率
- 风格是否偏朴素叙事而不是现代口语

### 5. Memory
适合测：
- 记住用户偏好
- 记住当前阅读范围
- 记住“不剧透”限制

### 6. Safety / Governance
适合测：
- prompt injection 隔离
- 版权控制
- 不确定时不瞎编

### 7. Resilience / Fallback
适合测：
- 索引缺失后的回退
- 多模态输入不掉线
- 工具失败后的恢复

---

## 推荐评测方式

### A. 可确定题
例如：
- 韩立为什么去参加七玄门测试？
- 炼骨崖分哪三段？
- 象甲功有哪些特点？

可用：
- 关键词命中
- 禁止词检查
- 章节范围检查

### B. 半结构化题
例如：
- 给墨大夫做人物卡
- 整理神秘瓶子时间线

可用：
- required fields
- required points
- 顺序检查

### C. 开放生成题
例如：
- 按前14章风格续写
- 保持人物一致性

可用：
- checklist + forbidden points
- 规则判分
- 后续再接 LLM-as-a-judge

---

## 预测文件格式建议

`predictions.jsonl` 每行一条：

```json
{"id":"qa_001","planner":{"task_type":"qa","retrieval_needed":true,"retrieval_targets":["chapter_chunks","event_timeline"]},"answer":"因为韩立的三叔……","evidence":[{"chapter":1,"quote":"……"}]}
```

---

## 落地建议

先用这套数据把你的系统跑出第一版基线：

- `baseline_direct_context`
- `baseline_basic_rag`
- `your_planner_retrieval_memory_system`

至少对比这几类指标：

- QA 正确率
- groundedness
- 幻觉率
- 设定冲突率
- 续写违规率
- planner 命中率

这样你在简历和面试里就能讲：

> 我不是只做了一个 demo，我把系统拆成 Planner / Retrieval / Memory / Validation 几层，并且用结构化测试集和自动评测脚本去验证问答、续写、安全和恢复链路。

---

## 建议先跑的核心 case

如果你想先快速验证系统，优先跑这些：

- `qa_001` ~ `qa_010`
- `planner_001`
- `planner_002`
- `cont_001`
- `memory_002`
- `safety_001`
- `safety_003`
- `resilience_001`

这 16 个 case 已经能很好地区分“能聊天”和“有工程度”的系统。