from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from novel_system.api import create_app
from novel_system.config import ROOT_DIR, AppConfig
from novel_system.service import NovelSystemService


def sample_book(chapters: int) -> str:
    blocks: list[str] = []
    for chapter in range(1, chapters + 1):
        blocks.append(
            "\n".join(
                [
                    f"第{chapter}章 章节{chapter}",
                    f"韩立在第{chapter}章来到七玄门，张铁和墨大夫也在这里。",
                    "这段文字用来生成分章、摘要、时间线和人物卡。",
                    "厉飞雨提到口诀、修炼和考核，方便检索系统提取事件。",
                ]
            )
        )
    return "\n\n".join(blocks)


class BookImportArtifactsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        base_dir = Path(self.temp_dir.name)
        self.data_dir = base_dir / "data"
        self.runtime_dir = self.data_dir / "runtime"
        self.books_dir = self.data_dir / "books"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.books_dir.mkdir(parents=True, exist_ok=True)

        self.default_book_path = base_dir / "default-book.txt"
        self.default_book_path.write_text(sample_book(2), encoding="utf-8")

        self.config = AppConfig(
            root_dir=ROOT_DIR,
            data_dir=self.data_dir,
            runtime_dir=self.runtime_dir,
            books_dir=self.books_dir,
            default_book_id="default-book",
            default_book_title="默认测试书",
            default_book_path=self.default_book_path,
            minimax_api_key="",
            minimax_base_url="https://api.minimax.chat/v1",
            minimax_chat_model="MiniMax-m2.7-HighSpeed",
            embedding_provider="local_openvino",
            local_embedding_model="BAAI/bge-small-zh-v1.5",
            local_embedding_device="CPU",
            local_embedding_fallback_device="CPU",
            local_embedding_batch_size=32,
            local_embedding_normalize=True,
            local_embedding_cache_dir=self.runtime_dir / "models",
            trace_enabled=True,
            trace_log_level="INFO",
        )
        self.service = NovelSystemService(self.config)

        self.config_patch = patch("novel_system.api.AppConfig.load", return_value=self.config)
        self.service_patch = patch("novel_system.api.create_service", return_value=self.service)
        self.config_patch.start()
        self.service_patch.start()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.client.close()
        self.service_patch.stop()
        self.config_patch.stop()
        self.temp_dir.cleanup()

    def upload_book(self, filename: str, content: str):
        response = self.client.post(
            "/api/books",
            files={"file": (filename, content.encode("utf-8"), "text/plain")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def wait_until_ready(self, book_id: str) -> dict:
        self.client.post(f"/api/books/{book_id}/start-index").raise_for_status()
        last_payload = None
        for _ in range(200):
            response = self.client.get(f"/api/books/{book_id}/status")
            response.raise_for_status()
            last_payload = response.json()
            if last_payload["status"] == "ready":
                return last_payload
            if last_payload["status"] == "error":
                self.fail(f"indexing failed: {last_payload}")
            time.sleep(0.03)
        self.fail(f"indexing did not finish: {last_payload}")

    def test_reupload_resets_manifest_and_clears_old_artifacts(self) -> None:
        filename = "same-name-book.txt"
        first_manifest = self.upload_book(filename, sample_book(4))
        book_id = first_manifest["id"]
        self.wait_until_ready(book_id)

        second_response = self.upload_book(filename, sample_book(1))

        self.assertEqual(second_response["id"], book_id)
        self.assertEqual(second_response["status"], "pending")
        self.assertFalse(second_response["indexed"])
        self.assertEqual(second_response["chapter_count"], 0)
        self.assertEqual(second_response["chunk_count"], 0)

        status_response = self.client.get(f"/api/books/{book_id}/status")
        status_response.raise_for_status()
        self.assertEqual(status_response.json()["status"], "pending")

        artifact_dir = self.books_dir / book_id
        self.assertTrue((artifact_dir / "manifest.json").exists())
        self.assertFalse((artifact_dir / "chapters.json").exists())

    def test_artifact_endpoints_return_catalog_and_preview(self) -> None:
        manifest = self.upload_book("artifact-view-book.txt", sample_book(3))
        book_id = manifest["id"]
        self.wait_until_ready(book_id)

        catalog_response = self.client.get(f"/api/books/{book_id}/artifacts")
        self.assertEqual(catalog_response.status_code, 200, catalog_response.text)
        catalog = catalog_response.json()

        artifact_names = [item["name"] for item in catalog["artifacts"]]
        self.assertIn("manifest", artifact_names)
        self.assertIn("chapters", artifact_names)
        self.assertIn("chapter_summaries", artifact_names)

        preview_response = self.client.get(f"/api/books/{book_id}/artifacts/chapter_summaries")
        self.assertEqual(preview_response.status_code, 200, preview_response.text)
        preview = preview_response.json()

        self.assertEqual(preview["artifact"]["name"], "chapter_summaries")
        self.assertEqual(preview["total_count"], 3)
        self.assertFalse(preview["truncated"])
        self.assertEqual(preview["content"][0]["chapter"], 1)


if __name__ == "__main__":
    unittest.main()
