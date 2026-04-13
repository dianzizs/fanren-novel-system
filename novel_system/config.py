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
    # Tracing 配置
    trace_enabled: bool
    trace_log_level: str

    @classmethod
    def load(cls) -> "AppConfig":
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
            # Tracing 配置
            trace_enabled=os.getenv("TRACE_ENABLED", "true").lower() == "true",
            trace_log_level=os.getenv("TRACE_LOG_LEVEL", "INFO"),
        )

