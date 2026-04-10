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


@dataclass(slots=True)
class AppConfig:
    root_dir: Path
    data_dir: Path
    runtime_dir: Path
    books_dir: Path
    default_book_id: str
    default_book_title: str
    default_book_path: Path
    minimax_api_key: str
    minimax_base_url: str
    minimax_chat_model: str

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
            default_book_id=os.getenv("DEFAULT_BOOK_ID", "fanren-1-500"),
            default_book_title=os.getenv("DEFAULT_BOOK_TITLE", "凡人修仙传（1-500章）"),
            default_book_path=Path(
                os.getenv(
                    "DEFAULT_BOOK_PATH",
                    str(ROOT_DIR / "凡人修仙传(1-500章).txt"),
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
        )

