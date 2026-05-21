"""Tests for LLM-based candidate name filtering during indexing."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from novel_system.config import AppConfig
from novel_system.indexing import BookIndexRepository


def _make_config(tmp_path: Path, api_key: str = "") -> AppConfig:
    data_dir = tmp_path / "data"
    return AppConfig(
        root_dir=tmp_path,
        data_dir=data_dir,
        runtime_dir=data_dir / "runtime",
        books_dir=data_dir / "books",
        default_book_id="default-book",
        default_book_title="Default",
        default_book_path=tmp_path / "default.txt",
        minimax_api_key=api_key,
        minimax_base_url="https://api.minimax.chat/v1",
        minimax_chat_model="MiniMax-m2.7-HighSpeed",
        embedding_provider="local_openvino",
        local_embedding_model="BAAI/bge-small-zh-v1.5",
        local_embedding_device="CPU",
        local_embedding_fallback_device="CPU",
        local_embedding_batch_size=32,
        local_embedding_normalize=True,
        local_embedding_cache_dir=tmp_path / "cache",
        vector_store_dir=data_dir / "vectors",
        trace_enabled=False,
        trace_log_level="INFO",
        dense_search_overfetch_factor=10,
    )


class TestFilterNamesWithLlm:
    """Tests for BookIndexRepository._filter_names_with_llm."""

    def test_returns_all_names_when_api_key_empty(self, tmp_path: Path):
        config = _make_config(tmp_path, api_key="")
        repo = BookIndexRepository(config)
        names = ["韩立", "时间", "南宫婉", "方法"]
        result = repo._filter_names_with_llm(names)
        assert result == set(names)

    def test_filters_names_via_llm(self, tmp_path: Path):
        config = _make_config(tmp_path, api_key="test-key")
        repo = BookIndexRepository(config)

        names = ["韩立", "时间", "南宫婉", "成功", "银月", "方法"]
        with patch("novel_system.llm.MiniMaxClient") as MockClient:
            instance = MockClient.return_value
            instance.enabled = True
            instance.chat.return_value = MagicMock(content="韩立、南宫婉、银月", usage=None)

            result = repo._filter_names_with_llm(names)
            assert result == {"韩立", "南宫婉", "银月"}

    def test_returns_all_names_on_api_failure(self, tmp_path: Path):
        config = _make_config(tmp_path, api_key="test-key")
        repo = BookIndexRepository(config)

        names = ["韩立", "时间", "南宫婉"]
        with patch("novel_system.llm.MiniMaxClient") as MockClient:
            instance = MockClient.return_value
            instance.enabled = True
            instance.chat.side_effect = RuntimeError("API error")

            result = repo._filter_names_with_llm(names)
            assert result == set(names)

    def test_handles_batching(self, tmp_path: Path):
        config = _make_config(tmp_path, api_key="test-key")
        repo = BookIndexRepository(config)

        names = [f"韩{i}立" for i in range(120)]

        with patch("novel_system.llm.MiniMaxClient") as MockClient:
            instance = MockClient.return_value
            instance.enabled = True
            instance.chat.side_effect = [
                MagicMock(content="韩0立", usage=None),
                MagicMock(content="韩50立", usage=None),
                MagicMock(content="韩100立", usage=None),
            ]

            result = repo._filter_names_with_llm(names, batch_size=50)
            assert instance.chat.call_count == 3
            assert "韩0立" in result
            assert "韩50立" in result
            assert "韩100立" in result

    def test_handles_no_valid_names(self, tmp_path: Path):
        config = _make_config(tmp_path, api_key="test-key")
        repo = BookIndexRepository(config)

        names = ["韩立", "时间"]
        with patch("novel_system.llm.MiniMaxClient") as MockClient:
            instance = MockClient.return_value
            instance.enabled = True
            instance.chat.return_value = MagicMock(content="无", usage=None)

            result = repo._filter_names_with_llm(names)
            assert result == set()

    def test_handles_comma_separator(self, tmp_path: Path):
        """LLM may return comma instead of enumeration mark."""
        config = _make_config(tmp_path, api_key="test-key")
        repo = BookIndexRepository(config)

        names = ["韩立", "时间", "南宫婉"]
        with patch("novel_system.llm.MiniMaxClient") as MockClient:
            instance = MockClient.return_value
            instance.enabled = True
            instance.chat.return_value = MagicMock(content="韩立，南宫婉", usage=None)

            result = repo._filter_names_with_llm(names)
            assert result == {"韩立", "南宫婉"}
