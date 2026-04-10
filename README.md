# 凡人修仙传长文本系统

基于 playbook 落地的长文本小说系统，围绕《凡人修仙传》1-500 章提供：

- TXT ingestion、章节切分、chunk 化
- chapter summary / event timeline / character card / canon memory 索引
- planner + retrieval + memory + validation
- grounded QA、结构化抽取、约束续写
- FastAPI API 与本地工作台
- 评测脚本接入 `fanren_eval_cases_v1.jsonl`

## 快速开始

1. 安装依赖

```bash
python -m pip install -r requirements.txt
```

2. 配置环境变量

```bash
copy .env.example .env
```

然后在 `.env` 中填入 `MINIMAX_API_KEY`。

3. 构建索引

```bash
python scripts/build_index.py
```

4. 启动工作台

```bash
python scripts/run_api.py
```

打开 `http://127.0.0.1:8000`。

5. 运行评测

```bash
python scripts/run_eval.py
```

评测结果会写入 `data/runtime/eval_report.json`，工作台里的 Evaluation Dashboard 会自动读取。

## 核心接口

- `POST /api/books`
- `POST /api/books/{id}/index`
- `POST /api/books/{id}/ask`
- `POST /api/books/{id}/continue`
- `GET/PUT /api/books/{id}/canon`
- `GET /api/books/{id}/timeline`

## 目录

```text
novel_system/
  api.py
  config.py
  indexing.py
  llm.py
  models.py
  planner.py
  retrieval.py
  service.py
scripts/
  build_index.py
  run_api.py
  run_eval.py
templates/
static/
```

