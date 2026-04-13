# 小王一号 - 小说问答系统

## 项目概述

这是一个基于 FastAPI 的小说问答系统，支持对小说内容进行问答、续写等操作。

## 环境配置

**重要：本项目使用 conda 的 chaishu 环境**

运行 Python 命令时，必须使用：
```bash
conda run -n chaishu python <command>
```

或者激活环境后运行：
```bash
conda activate chaishu
python <command>
```

## 常用命令

### 启动服务
```bash
conda run -n chaishu python -m novel_system.api
```

### 运行测试
```bash
conda run -n chaishu python -m pytest
```

### 安装依赖
```bash
conda run -n chaishu pip install -r requirements.txt
```

## 代码结构

- `novel_system/service.py` - 核心服务逻辑，包含 `ask()` 和 `continue_story()` 函数
- `novel_system/models.py` - Pydantic 数据模型
- `novel_system/planner.py` - 查询规划和重写
- `novel_system/retrieval.py` - 检索逻辑
- `novel_system/tracing.py` - 追踪日志基础设施

## Tracing 功能

系统已集成追踪功能，可通过 `debug=true` 参数启用：

```bash
curl -X POST "http://localhost:8000/api/books/{book_id}/ask" \
  -H "Content-Type: application/json" \
  -d '{"user_query": "问题内容", "debug": true}'
```

环境变量控制：
- `TRACE_ENABLED=true` - 启用追踪日志
- `TRACE_LOG_LEVEL=INFO` - 日志级别
