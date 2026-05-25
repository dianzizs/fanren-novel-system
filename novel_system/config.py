"""应用配置模块。

从环境变量加载配置，包括 LLM、Embedding、路径等设置。

关键导出：
- AppConfig: 应用配置类
- ROOT_DIR: 项目根目录路径
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass
class AppConfig:
    """应用配置，包含所有模块的配置项。

    通过 load() 类方法从环境变量加载配置。
    """

    root_dir: Path
    data_dir: Path
    runtime_dir: Path
    books_dir: Path
    default_book_id: str
    default_book_title: str
    default_book_path: Path
    # MiniMax 配置（仅用于 chat）
    minimax_api_key: str
    minimax_base_url: str
    minimax_chat_model: str
    # 本地 Embedding 配置
    embedding_provider: str
    local_embedding_model: str
    local_embedding_device: str
    local_embedding_fallback_device: str
    local_embedding_batch_size: int
    local_embedding_normalize: bool
    local_embedding_cache_dir: Path
    # 向量存储目录（避免中文路径问题）
    vector_store_dir: Path
    # Tracing 配置
    trace_enabled: bool
    trace_log_level: str
    # Dense search 配置
    dense_search_overfetch_factor: int
    # Reranker 配置
    rerank_enabled: bool = True
    reranker_type: str = "rule_based"
    # Mimo 配置（Anthropic-compatible 备用 LLM）
    mimo_api_key: str = ""
    mimo_base_url: str = "https://token-plan-cn.xiaomimimo.com/anthropic"
    mimo_chat_model: str = "mimo-v2.5"
    # GraphRAG 配置
    graphrag_workspace_name: str = "graphrag"
    graphrag_use_cli_for_index: bool = True
    graphrag_python_executable: str = "graphrag"
    graphrag_index_timeout_sec: int = 7200
    graphrag_default_search_mode: str = "auto"
    graphrag_enable_claims: bool = True
    graphrag_embedding_api_base: str = "http://localhost:8000/v1"
    graphrag_embedding_model: str = "Qwen/Qwen3-Embedding-4B"
    graphrag_chat_model: str = "MiniMax-m2.7-HighSpeed"
    graphrag_chat_api_base: str = "https://api.minimax.chat/v1"
    graphrag_api_key: str = ""

    @classmethod
    def load(cls) -> "AppConfig":
        """从环境变量加载配置。

        优先读取 .env 文件，然后读取系统环境变量。

        Returns:
            配置完成的 AppConfig 实例
        """
        _load_dotenv(ROOT_DIR / ".env")
        data_dir = ROOT_DIR / "data"
        runtime_dir = data_dir / "runtime"
        books_dir = data_dir / "books"
        return cls(
            root_dir=ROOT_DIR,
            data_dir=data_dir,
            runtime_dir=runtime_dir,
            books_dir=books_dir,
            default_book_id=os.getenv("DEFAULT_BOOK_ID", "default-book"),
            default_book_title=os.getenv("DEFAULT_BOOK_TITLE", "默认小说"),
            default_book_path=Path(
                os.getenv(
                    "DEFAULT_BOOK_PATH",
                    str(ROOT_DIR / "default-book.txt"),
                )
            ),
            minimax_api_key=os.getenv("MINIMAX_API_KEY", "").strip(),
            minimax_base_url=os.getenv(
                "MINIMAX_BASE_URL",
                "https://api.minimax.chat/v1",
            ).rstrip("/"),
            minimax_chat_model=os.getenv(
                "MINIMAX_CHAT_MODEL",
                "MiniMax-m2.7-HighSpeed",
            ),
            mimo_api_key=(os.getenv("MIMO_API_KEY", "") or os.getenv("ANTHROPIC_AUTH_TOKEN", "")).strip(),
            mimo_base_url=(os.getenv(
                "MIMO_BASE_URL",
                "",
            ) or os.getenv("ANTHROPIC_BASE_URL", "") or "https://token-plan-cn.xiaomimimo.com/anthropic").rstrip("/"),
            mimo_chat_model=(os.getenv("MIMO_CHAT_MODEL", "") or "mimo-v2.5").strip(),
            # 本地 Embedding 配置
            embedding_provider=os.getenv("EMBEDDING_PROVIDER", "local_openvino"),
            local_embedding_model=os.getenv(
                "LOCAL_EMBEDDING_MODEL",
                "BAAI/bge-small-zh-v1.5",
            ),
            local_embedding_device=os.getenv("LOCAL_EMBEDDING_DEVICE", "GPU"),
            local_embedding_fallback_device=os.getenv("LOCAL_EMBEDDING_FALLBACK_DEVICE", "CPU"),
            local_embedding_batch_size=int(os.getenv("LOCAL_EMBEDDING_BATCH_SIZE", "32")),
            local_embedding_normalize=os.getenv("LOCAL_EMBEDDING_NORMALIZE", "true").lower() == "true",
            local_embedding_cache_dir=Path(
                os.getenv("LOCAL_EMBEDDING_CACHE_DIR", str(runtime_dir / "models"))
            ),
            # 向量存储目录（避免中文路径问题）
            vector_store_dir=Path(
                os.getenv("VECTOR_STORE_DIR", str(data_dir / "vectors"))
            ),
            # Tracing 配置
            trace_enabled=os.getenv("TRACE_ENABLED", "true").lower() == "true",
            trace_log_level=os.getenv("TRACE_LOG_LEVEL", "INFO"),
            # Dense search 配置
            dense_search_overfetch_factor=int(os.getenv("DENSE_SEARCH_OVERFETCH_FACTOR", "10")),
            # Reranker 配置
            rerank_enabled=os.getenv("RERANK_ENABLED", "true").lower() == "true",
            reranker_type=os.getenv("RERANKER_TYPE", "rule_based"),
            # GraphRAG 配置
            graphrag_workspace_name=os.getenv("GRAPHRAG_WORKSPACE_NAME", "graphrag"),
            graphrag_use_cli_for_index=os.getenv("GRAPHRAG_USE_CLI_FOR_INDEX", "true").lower() == "true",
            graphrag_python_executable=os.getenv("GRAPHRAG_PYTHON_EXECUTABLE", "graphrag"),
            graphrag_index_timeout_sec=int(os.getenv("GRAPHRAG_INDEX_TIMEOUT_SEC", "7200")),
            graphrag_default_search_mode=os.getenv("GRAPHRAG_DEFAULT_SEARCH_MODE", "auto"),
            graphrag_enable_claims=os.getenv("GRAPHRAG_ENABLE_CLAIMS", "true").lower() == "true",
            graphrag_embedding_api_base=os.getenv("GRAPHRAG_EMBEDDING_API_BASE", "http://localhost:8000/v1"),
            graphrag_embedding_model=os.getenv("GRAPHRAG_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-4B"),
            graphrag_chat_model=os.getenv("GRAPHRAG_CHAT_MODEL", "MiniMax-m2.7-HighSpeed"),
            graphrag_chat_api_base=os.getenv("GRAPHRAG_CHAT_API_BASE", "https://api.minimax.chat/v1"),
            graphrag_api_key=os.getenv("GRAPHRAG_API_KEY", os.getenv("MINIMAX_API_KEY", "")),
        )
