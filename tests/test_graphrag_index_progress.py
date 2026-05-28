import json

from novel_system.config import AppConfig
from novel_system.graphrag_app.paths import graphrag_root
from novel_system.indexing import BookIndexRepository
from novel_system.services.indexing import IndexingServiceMixin


class IndexingStatusService(IndexingServiceMixin):
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.repo = BookIndexRepository(config)


def test_status_uses_graphrag_extract_graph_progress(test_config: AppConfig):
    service = IndexingStatusService(test_config)
    book_id = "book-a"
    book_dir = test_config.books_dir / book_id
    book_dir.mkdir(parents=True)
    (book_dir / "manifest.json").write_text(
        json.dumps(
            {
                "id": book_id,
                "title": "Book A",
                "source_path": "book-a.txt",
                "status": "indexing",
                "index_progress": 0.3,
            }
        ),
        encoding="utf-8",
    )
    log_dir = graphrag_root(test_config, book_id) / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "indexing-engine.log").write_text(
        "2026-05-25 21:31:23 - INFO - graphrag.logger.progress - extract graph progress: 20/42\n",
        encoding="utf-8",
    )

    status = service.get_book_status(book_id)

    assert status["progress"] > 0.3
    assert status["progress"] < 0.85
    assert status["message"] == "正在抽取实体关系... (20/42)"


def test_status_uses_graphrag_description_summary_progress(test_config: AppConfig):
    service = IndexingStatusService(test_config)
    book_id = "book-b"
    book_dir = test_config.books_dir / book_id
    book_dir.mkdir(parents=True)
    (book_dir / "manifest.json").write_text(
        json.dumps(
            {
                "id": book_id,
                "title": "Book B",
                "source_path": "book-b.txt",
                "status": "indexing",
                "index_progress": 0.3,
            }
        ),
        encoding="utf-8",
    )
    log_dir = graphrag_root(test_config, book_id) / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "indexing-engine.log").write_text(
        "\n".join(
            [
                "2026-05-25 21:32:37 - INFO - graphrag.logger.progress - extract graph progress: 42/42",
                "2026-05-25 21:32:38 - INFO - graphrag.logger.progress - Summarize entity/relationship description progress: 31/987",
            ]
        ),
        encoding="utf-8",
    )

    status = service.get_book_status(book_id)

    assert status["progress"] > 0.5
    assert status["progress"] < 0.85
    assert status["message"] == "正在汇总实体关系描述... (31/987)"
