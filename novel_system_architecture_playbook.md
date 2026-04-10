# 长文本小说拆书、问答与续写系统文档

## 项目定位
这是一个面向长文本小说场景的 AI 内容系统，目标是把 **拆书、内容问答、设定约束续写** 做成一个可投简历、可讲工程设计、可扩展前端工作台的项目，而不是单一 Prompt Demo。

> 一句话定位：把续写问题改造成“检索 + 约束 + 验证”的系统工程问题。

## 核心架构
1. **Ingestion**：解析 PDF / EPUB / TXT / 图片，完成切章与 chunk 化  
2. **Knowledge Extraction**：抽取人物、事件、关系、世界规则、时间线与章节摘要  
3. **Planner**：识别任务类型，决定要不要检索与检索深度  
4. **Retrieval**：章节摘要索引、原文 chunk、角色卡、时间线、canon memory  
5. **Execution**：Summary Skill / QA Skill / Continuation Skill  
6. **Validation**：groundedness、设定冲突检查、风险审查  
7. **Frontend Workspace**：阅读、提问、笔记、知识卡片、续写与版本对比

## 模块说明
### 文档接入层
- 解析 PDF / EPUB / TXT / 图片
- OCR 与视觉理解兜底
- 输出规范化文本、章节与元数据

### 结构化抽取层
- 人物卡、世界观卡、章节摘要
- 事件链、地点、关系、时间线
- 每个 Skill 都应该能单测

### Planner
至少输出以下字段：
- `task_type`
- `retrieval_needed`
- `retrieval_targets`
- `constraints`
- `success_criteria`

### Retrieval
- 问答：Hybrid Retrieval + rerank
- 跨章节问题：事件链 / 时间线优先
- 人物关系：人物卡、关系图优先
- 续写：最近剧情 + 人物状态 + 世界规则 + 文风样本优先

### Memory
- 用户偏好记忆：题材、风格、回答长度
- 会话工作记忆：当前书、当前章节、最近问题
- 项目 Canon Memory：世界规则、已发生事件、未回收伏笔

### QA Skill
- 基于证据回答
- 返回引用片段
- 不确定时明确标注

### Continuation Skill
- 基于约束生成续写
- 支持多候选版本
- 生成前后都做设定冲突检查

### Safety & Governance
- prompt injection 隔离
- 引用长度限制
- MCP 白名单、参数校验、日志审计

### Evaluation
- QA 正确率
- Groundedness
- 幻觉率
- 设定冲突率
- 文风贴合度
- 情节连贯性

## 前端工作台设计
### 推荐技术栈
- Next.js 15
- TypeScript
- Tailwind CSS
- shadcn/ui
- Zustand
- TanStack Query
- TipTap

### 页面结构
#### Library
- 上传书籍
- 查看索引进度
- 进入项目

#### Reader Workspace
- 左侧：章节目录
- 中间：正文阅读区
- 右侧：Ask Panel

#### Knowledge View
- 人物卡
- 世界观
- 时间线
- 关系图

#### Continuation Studio
- 约束面板
- 生成结果
- 多版本对比
- 接受草稿

#### Evaluation Dashboard
- baseline 对比
- 失败案例
- 指标图表

### 核心组件
- `BookUploadCard`
- `ProcessingStatusCard`
- `ChapterTree`
- `ReaderPane`
- `AskPanel`
- `EvidenceCard`
- `CharacterCard`
- `TimelineBoard`
- `ContinuationEditor`
- `VersionCompare`

### 核心 API
- `POST /api/books`
- `POST /api/books/{id}/index`
- `POST /api/books/{id}/ask`
- `POST /api/books/{id}/continue`
- `GET/PUT /api/books/{id}/canon`
- `GET /api/books/{id}/timeline`

## 简历写法
### 一句话
搭建面向长文本小说场景的 AI 内容系统，将拆书、证据问答与设定约束续写统一到“内容结构化—任务规划—分层检索—一致性校验”的工程链路中。

### 简历项目描述
- 针对长文本内容场景下“信息跨章节分散、事实问答易漂移、续写难以持续遵守人物与设定约束”等问题，设计并落地“文档接入—结构化抽取—任务规划—分层检索—回答/续写生成—一致性校验”的完整系统。
- 构建人物卡、世界观卡、事件链、时间线与章节摘要等结构化索引，区分事实问答检索与续写检索策略，并通过 Planner-Executor 分工提升链路可解释性与可扩展性。
- 设计 grounded QA 与 continuation evaluation 评估体系，以 QA 正确率、引用一致性、设定冲突率、文风贴合度等指标对比 baseline，验证系统在长文本场景下的稳定性提升。

## 面试讲法
### 60 秒版
我做这个项目时发现，长文本小说场景最大的问题不是模型不会写，而是它在跨章节问答和持续续写时不稳定：一方面信息分散，直接问模型容易遗漏；另一方面事实问答和创意续写对上下文要求完全不同，不能共用一套简单 RAG。  
所以我把系统拆成内容结构化、任务规划、分层检索、分层记忆和一致性校验几层。问答时强调证据召回和 groundedness，续写时强调最近剧情、人物状态、世界规则和文风样本，并在生成前后都做冲突检查。我的重点不是把它做成一个会聊天的 demo，而是把生成问题改造成一个可评估、可恢复、可治理的工程链路。

## 给 Cursor / Claude Code 的前端提示词
```text
请帮我从 0 到 1 搭建一个面向长文本小说场景的前端工作台，技术栈使用 Next.js + TypeScript + Tailwind + shadcn/ui。
目标产品包含 5 个核心页面：Library、Reader Workspace、Knowledge View、Continuation Studio、Evaluation Dashboard。
核心要求：
1) Reader Workspace 采用左侧章节目录、中间正文阅读区、右侧 Ask Panel 的三栏布局；
2) 支持上传书籍、展示解析状态、查看章节摘要、人物卡、世界观卡、时间线；
3) Ask Panel 要显示答案、证据卡片、引用高亮与不确定性标签；
4) Continuation Studio 要支持约束面板、多版本续写、版本对比与接受草稿；
5) 页面组件风格保持简洁、偏专业工作台，不要做成花哨营销页；
6) 先用 mock data 跑通，再预留对接 /api/books、/api/books/{id}/ask、/api/books/{id}/continue 等接口；
7) 组件拆分要清晰，状态管理使用 Zustand + TanStack Query，目录结构要规范；
8) 先交付可运行的页面骨架、mock 数据、类型定义和组件树，再逐步补交互细节。
```
