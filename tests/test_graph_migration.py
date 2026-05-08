"""Tests for graph naming policy migration verification.

These tests verify the one-shot migration from hardcoded constants
to profile-based configuration is complete and correct.

Key paths covered:
- Configuration loading fallback
- Alias merging
- Candidate filtering
- Whitelist determination
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from novel_system.graph_name_policy import (
    GraphProfile,
    load_graph_profile,
    normalize_name,
    normalize_name_with_profile,
    resolve_aliases,
    resolve_aliases_with_profile,
    filter_candidates,
    filter_candidates_with_profile,
    get_effective_seeds_and_aliases,
    is_book_in_whitelist,
    get_policy_mode,
    build_profile_from_character_registry,
    GRAPH_WHITELIST,
)


class TestSampleBookVerification:
    """Tests verifying migration effect on sample book 凡人修仙传."""

    @pytest.fixture
    def sample_profile(self):
        """Load the actual graph_profile.json for 凡人修仙传."""
        from novel_system.config import AppConfig
        config = AppConfig.load()
        profile_path = config.data_dir / "books" / "凡人修仙传" / "graph_profile.json"
        if profile_path.exists():
            return load_graph_profile("凡人修仙传")
        return None

    def test_sample_book_profile_loads(self, sample_profile):
        """Sample book profile should load successfully."""
        if sample_profile is None:
            pytest.skip("Sample book profile not found")
        assert sample_profile.book_id == "凡人修仙传"
        assert len(sample_profile.character_seeds) > 0
        assert len(sample_profile.aliases) > 0

    def test_sample_book_alias_merging(self, sample_profile):
        """Sample book aliases should merge correctly."""
        if sample_profile is None:
            pytest.skip("Sample book profile not found")

        # Known aliases from graph_profile.json
        assert resolve_aliases_with_profile("二愣子", sample_profile) == "韩立"
        assert resolve_aliases_with_profile("墨老", sample_profile) == "墨大夫"
        assert resolve_aliases_with_profile("三叔", sample_profile) == "韩胖子"
        assert resolve_aliases_with_profile("韩立三叔", sample_profile) == "韩胖子"

    def test_sample_book_filtering(self, sample_profile):
        """Sample book filtering should work correctly."""
        if sample_profile is None:
            pytest.skip("Sample book profile not found")

        known_names = sample_profile.character_seeds

        # Valid names should pass
        assert normalize_name_with_profile("韩立", known_names, sample_profile) == "韩立"
        assert normalize_name_with_profile("张铁", known_names, sample_profile) == "张铁"

        # Aliases should resolve
        assert normalize_name_with_profile("二愣子", known_names, sample_profile) == "韩立"

        # Generic names should be filtered
        assert normalize_name_with_profile("时间", known_names, sample_profile) is None
        assert normalize_name_with_profile("方法", known_names, sample_profile) is None

    def test_sample_book_alias_validity(self, sample_profile):
        """All aliases should point to valid seeds."""
        if sample_profile is None:
            pytest.skip("Sample book profile not found")

        for alias, canonical in sample_profile.aliases.items():
            assert canonical in sample_profile.character_seeds, \
                f"Alias {alias} -> {canonical} but {canonical} not in seeds"

    def test_sample_book_whitelist(self, sample_profile):
        """Sample book should be in whitelist with profile mode."""
        if sample_profile is None:
            pytest.skip("Sample book profile not found")

        assert is_book_in_whitelist("凡人修仙传") is True
        assert get_policy_mode("凡人修仙传") == "profile"


class TestMigrationConfigLoadingFallback:
    """Tests for configuration loading with fallback behavior."""

    def test_load_missing_profile_returns_empty(self, tmp_path: Path):
        """Loading a missing profile should return empty profile.

        IMPORTANT: No book-specific defaults - prevents cross-book contamination.
        """
        book_dir = tmp_path / "missing-book"
        book_dir.mkdir(parents=True)

        profile = load_graph_profile("missing-book", data_dir=tmp_path)

        # Should be empty, not contaminated with book-specific defaults
        assert profile.character_seeds == set()
        assert profile.aliases == {}

    def test_load_invalid_json_returns_empty(self, tmp_path: Path):
        """Invalid JSON should fall back to empty profile gracefully."""
        book_dir = tmp_path / "bad-book"
        book_dir.mkdir(parents=True)
        (book_dir / "graph_profile.json").write_text("{ bad json", encoding="utf-8")

        profile = load_graph_profile("bad-book", data_dir=tmp_path)

        assert profile.book_id == "bad-book"
        assert profile.character_seeds == set()
        assert profile.aliases == {}

    def test_load_valid_profile_overrides_defaults(self, tmp_path: Path):
        """Valid profile should provide custom seeds/aliases."""
        book_dir = tmp_path / "custom-book"
        book_dir.mkdir(parents=True)
        profile_data = {
            "book_id": "custom-book",
            "character_seeds": ["张三", "李四"],
            "aliases": {"小张": "张三"},
            "manual_fixes": [],
        }
        (book_dir / "graph_profile.json").write_text(
            json.dumps(profile_data, ensure_ascii=False), encoding="utf-8"
        )

        profile = load_graph_profile("custom-book", data_dir=tmp_path)

        assert profile.character_seeds == {"张三", "李四"}
        assert profile.aliases == {"小张": "张三"}
        # Default seeds should NOT be present
        assert "韩立" not in profile.character_seeds


class TestMigrationAliasMerging:
    """Tests for alias merging correctness."""

    def test_resolve_aliases_without_profile_returns_name(self):
        """resolve_aliases without profile returns name unchanged.

        IMPORTANT: No profile means no alias resolution.
        """
        # Without profile, returns name unchanged
        assert resolve_aliases("二愣子") == "二愣子"
        assert resolve_aliases("墨老") == "墨老"

        # No alias - return as-is
        assert resolve_aliases("韩立") == "韩立"
        assert resolve_aliases("未知人物") == "未知人物"

    def test_resolve_aliases_with_profile_uses_custom(self):
        """resolve_aliases_with_profile should use profile aliases."""
        profile = GraphProfile(
            book_id="test",
            character_seeds={"张三"},
            aliases={"小张": "张三", "张三三": "张三"},
        )

        assert resolve_aliases_with_profile("小张", profile) == "张三"
        assert resolve_aliases_with_profile("张三三", profile) == "张三"

    def test_profile_aliases_override_defaults(self):
        """Profile aliases should take precedence when profile is provided."""
        profile = GraphProfile(
            book_id="test",
            character_seeds={"韩立"},
            aliases={"二愣子": "韩立", "小韩": "韩立"},
        )

        # Profile alias works
        assert resolve_aliases_with_profile("小韩", profile) == "韩立"

        # With None profile, uses defaults
        # Without profile, returns name unchanged
        assert resolve_aliases_with_profile("二愣子", None) == "二愣子"

    def test_build_profile_from_character_registry(self):
        """Profile should be buildable from character_registry artifact."""
        registry = [
            {"canonical_name": "韩立", "aliases": ["二愣子", "小韩"]},
            {"canonical_name": "张铁", "aliases": ["铁子"]},
        ]

        profile = build_profile_from_character_registry(registry, book_id="test")

        assert "韩立" in profile.character_seeds
        assert "张铁" in profile.character_seeds
        assert profile.aliases.get("二愣子") == "韩立"
        assert profile.aliases.get("小韩") == "韩立"
        assert profile.aliases.get("铁子") == "张铁"


class TestMigrationCandidateFiltering:
    """Tests for candidate filtering with profile support."""

    def test_filter_candidates_without_profile_returns_empty(self):
        """filter_candidates without profile should return empty known_names.

        IMPORTANT: No profile means no book-specific knowledge - prevents contamination.
        """
        character_docs = [
            (0, {"name": "韩立", "chapters": [1, 2, 3]}),
        ]
        event_docs = [(0, {"participants": ["韩立"]})]

        scores, known_names = filter_candidates({}, character_docs, event_docs)

        # Should be empty - no profile means no book-specific knowledge
        assert known_names == set()

    def test_filter_candidates_with_profile_uses_custom(self):
        """filter_candidates_with_profile should use profile seeds."""
        profile = GraphProfile(
            book_id="test",
            character_seeds={"张三", "李四"},
            aliases={"小三": "张三"},
        )

        character_docs = [(0, {"name": "张三", "chapters": [1, 2, 3]})]
        event_docs = [(0, {"participants": ["张三", "李四"]})]

        scores, known_names = filter_candidates_with_profile(
            {}, character_docs, event_docs, profile
        )

        assert "张三" in known_names
        assert "李四" in known_names

    def test_normalize_name_delegates_to_profile_version(self):
        """normalize_name should delegate to normalize_name_with_profile."""
        known_names = {"韩立", "张铁"}

        # Both should give same result with None profile
        result1 = normalize_name("二愣子", known_names)
        result2 = normalize_name_with_profile("二愣子", known_names, None)
        assert result1 == result2

    def test_filter_candidates_delegates_to_profile_version(self):
        """filter_candidates should delegate to filter_candidates_with_profile."""
        character_docs = [(0, {"name": "韩立", "chapters": [1, 2, 3]})]
        event_docs = [(0, {"participants": ["韩立"]})]

        scores1, known1 = filter_candidates({}, character_docs, event_docs)
        scores2, known2 = filter_candidates_with_profile(
            {}, character_docs, event_docs, None
        )

        assert known1 == known2


class TestMigrationWhitelistDetermination:
    """Tests for whitelist policy and mode determination."""

    def test_whitelist_contains_expected_books(self):
        """Whitelist should contain expected book IDs."""
        assert "凡人修仙传" in GRAPH_WHITELIST

    def test_is_book_in_whitelist_returns_correct_result(self):
        """is_book_in_whitelist should return correct boolean."""
        assert is_book_in_whitelist("凡人修仙传") is True
        assert is_book_in_whitelist("凡人修仙传-1-500章-txt") is True
        assert is_book_in_whitelist("unknown_book") is False

    def test_get_policy_mode_returns_correct_mode(self):
        """get_policy_mode should return correct mode."""
        assert get_policy_mode("凡人修仙传") == "profile"
        assert get_policy_mode("unknown_book") == "heuristic"


class TestMigrationNoDualTrackLogic:
    """Tests verifying no dual-track logic remains."""

    def test_old_functions_delegate_to_profile_versions(self):
        """Old functions should delegate to profile versions with None profile.

        This ensures there's no separate code path for the old functions.
        """
        # If the old functions delegate correctly, calling them should
        # produce the same result as calling the profile version with None
        known_names = {"韩立", "张铁"}

        # normalize_name
        assert normalize_name("二愣子", known_names) == normalize_name_with_profile(
            "二愣子", known_names, None
        )

        # resolve_aliases
        assert resolve_aliases("二愣子") == resolve_aliases_with_profile("二愣子", None)

        # filter_candidates
        character_docs = [(0, {"name": "韩立", "chapters": [1]})]
        event_docs = [(0, {"participants": ["韩立"]})]
        _, known1 = filter_candidates({}, character_docs, event_docs)
        _, known2 = filter_candidates_with_profile({}, character_docs, event_docs, None)
        assert known1 == known2

    def test_default_profile_is_empty(self):
        """GraphProfile.default() should return empty profile.

        IMPORTANT: No book-specific defaults - prevents cross-book contamination.
        """
        profile = GraphProfile.default()

        assert profile.character_seeds == set()
        assert profile.aliases == {}

    def test_get_effective_seeds_returns_correct_data(self):
        """get_effective_seeds_and_aliases should return correct data."""
        # With None, returns defaults (empty)
        seeds, aliases = get_effective_seeds_and_aliases(None)
        assert seeds == set()
        assert aliases == {}

        # With profile, returns profile data
        profile = GraphProfile(
            book_id="test",
            character_seeds={"张三"},
            aliases={"小三": "张三"},
        )
        seeds, aliases = get_effective_seeds_and_aliases(profile)
        assert seeds == {"张三"}
        assert aliases == {"小三": "张三"}


class TestCharacterCardsUseProfileAliases:
    """Tests verifying character cards use profile aliases, not ALIAS_MAP."""

    def _make_config(self, tmp_path: Path) -> "AppConfig":
        from novel_system.config import AppConfig
        data_dir = tmp_path / "data"
        return AppConfig(
            root_dir=tmp_path,
            data_dir=data_dir,
            runtime_dir=data_dir / "runtime",
            books_dir=data_dir / "books",
            default_book_id="default-book",
            default_book_title="Default",
            default_book_path=tmp_path / "default.txt",
            minimax_api_key="",
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

    def test_character_cards_use_profile_aliases(self, tmp_path: Path):
        """Character cards should use aliases from graph_profile.json."""
        from novel_system.indexing import BookIndexRepository

        config = self._make_config(tmp_path)
        book_dir = config.books_dir / "test-book"
        book_dir.mkdir(parents=True)
        profile_data = {
            "book_id": "test-book",
            "character_seeds": ["韩立"],
            "aliases": {"二愣子": "韩立", "小韩": "韩立"},
        }
        (book_dir / "graph_profile.json").write_text(
            json.dumps(profile_data, ensure_ascii=False), encoding="utf-8"
        )

        repo = BookIndexRepository(config)
        # Use text where names are followed by punctuation to avoid greedy regex issues
        chapters = [
            {
                "chapter": 1,
                "title": "第一章",
                "text": "韩立、张铁来到了山上。韩立、张铁开始修炼。",
                "paragraphs": [
                    "韩立、张铁来到了山上。",
                    "韩立、张铁开始修炼。",
                ],
            },
        ]
        cards = repo._build_character_cards(chapters, book_id="test-book")

        han_card = next(c for c in cards if c["name"] == "韩立")
        assert "二愣子" in han_card["aliases"]
        assert "小韩" in han_card["aliases"]

    def test_character_cards_fallback_without_profile(self, tmp_path: Path):
        """Character cards should work with empty profile when no config exists."""
        from novel_system.indexing import BookIndexRepository

        config = self._make_config(tmp_path)
        repo = BookIndexRepository(config)
        chapters = [
            {
                "chapter": 1,
                "title": "第一章",
                "text": "韩立、张铁来到了山上。",
                "paragraphs": ["韩立、张铁来到了山上。"],
            },
        ]
        cards = repo._build_character_cards(chapters, book_id="nonexistent")

        han_card = next(c for c in cards if c["name"] == "韩立")
        assert han_card["aliases"] == []  # No aliases without profile


class TestCharacterRegistryUsesProfile:
    """Tests verifying character registry loads profile by book_id."""

    def test_registry_loads_profile_by_book_id(self, tmp_path: Path):
        """Character registry should load graph_profile.json using book_id."""
        from novel_system.config import AppConfig
        from novel_system.indexing import BookIndexRepository

        data_dir = tmp_path / "data"
        config = AppConfig(
            root_dir=tmp_path,
            data_dir=data_dir,
            runtime_dir=data_dir / "runtime",
            books_dir=data_dir / "books",
            default_book_id="default-book",
            default_book_title="Default",
            default_book_path=tmp_path / "default.txt",
            minimax_api_key="",
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

        book_dir = config.books_dir / "test-book"
        book_dir.mkdir(parents=True)
        profile_data = {
            "book_id": "test-book",
            "character_seeds": ["韩立", "墨大夫"],
            "aliases": {"二愣子": "韩立", "墨老": "墨大夫"},
        }
        (book_dir / "graph_profile.json").write_text(
            json.dumps(profile_data, ensure_ascii=False), encoding="utf-8"
        )

        repo = BookIndexRepository(config)
        chapters = [
            {
                "chapter": 1,
                "title": "第一章",
                "text": "韩立、墨大夫来到了山上。" * 5,
                "paragraphs": ["韩立、墨大夫来到了山上。"] * 5,
            },
            {
                "chapter": 2,
                "title": "第二章",
                "text": "韩立、墨大夫开始修炼。" * 5,
                "paragraphs": ["韩立、墨大夫开始修炼。"] * 5,
            },
        ]
        cards = repo._build_character_cards(chapters, book_id="test-book")
        registry = repo._build_character_registry(chapters, cards, book_id="test-book")

        # Seeds from profile should be preserved in registry
        canonical_names = {entry["canonical_name"] for entry in registry}
        assert "韩立" in canonical_names
        assert "墨大夫" in canonical_names


class TestNoAliasMapDependency:
    """Tests verifying ALIAS_MAP is no longer in the graph pipeline."""

    def test_indexing_module_has_no_alias_map(self):
        """indexing.py should no longer define ALIAS_MAP."""
        import novel_system.indexing as indexing_mod
        assert not hasattr(indexing_mod, "ALIAS_MAP")

    def test_service_does_not_import_alias_map(self):
        """service.py should not import ALIAS_MAP."""
        import novel_system.service as service_mod
        assert not hasattr(service_mod, "ALIAS_MAP")

    def test_graph_name_policy_does_not_import_alias_map(self):
        """graph_name_policy.py should not import ALIAS_MAP."""
        import novel_system.graph_name_policy as policy_mod
        assert not hasattr(policy_mod, "ALIAS_MAP")


class TestOneShotMigrationVerification:
    """Tests verifying one-shot migration is complete - no legacy constants remain."""

    def test_graph_canon_seeds_removed(self):
        """GRAPH_CANON_SEEDS should be removed from graph_name_policy.py."""
        import novel_system.graph_name_policy as policy_mod
        assert not hasattr(policy_mod, "GRAPH_CANON_SEEDS"), (
            "GRAPH_CANON_SEEDS should be removed - data now in graph_profile.json"
        )

    def test_graph_alias_lookup_removed(self):
        """GRAPH_ALIAS_LOOKUP should be removed from graph_name_policy.py."""
        import novel_system.graph_name_policy as policy_mod
        assert not hasattr(policy_mod, "GRAPH_ALIAS_LOOKUP"), (
            "GRAPH_ALIAS_LOOKUP should be removed - data now in graph_profile.json"
        )

    def test_no_hardcoded_book_specific_names_in_generic_names(self):
        """GRAPH_GENERIC_NAMES should not contain book-specific character names."""
        import novel_system.graph_name_policy as policy_mod
        generic_names = policy_mod.GRAPH_GENERIC_NAMES
        # Book-specific names like "和韩立", "和张铁" should be removed
        book_specific = {"和韩立", "和张铁"}
        for name in book_specific:
            assert name not in generic_names, (
                f"'{name}' is book-specific and should not be in GRAPH_GENERIC_NAMES"
            )

    def test_profile_based_seeding_works_without_legacy_constants(self):
        """Profile-based seeding should work without legacy constants."""
        profile = GraphProfile(
            book_id="test",
            character_seeds={"韩立", "南宫婉"},
            aliases={"二愣子": "韩立"},
        )
        # Test that profile-based functions work correctly
        assert resolve_aliases_with_profile("二愣子", profile) == "韩立"
        assert resolve_aliases_with_profile("韩立", profile) == "韩立"
        assert resolve_aliases_with_profile("unknown", profile) == "unknown"

    def test_normalize_name_uses_profile_not_constants(self):
        """normalize_name_with_profile should use profile data, not legacy constants."""
        profile = GraphProfile(
            book_id="test",
            character_seeds={"韩立"},
            aliases={"二愣子": "韩立"},
        )
        known_names = {"韩立", "张铁"}
        # Should resolve alias via profile
        assert normalize_name_with_profile("二愣子", known_names, profile) == "韩立"
        # Should not find name that's only in legacy constants (if they existed)
        assert normalize_name_with_profile("未知角色", known_names, profile) is None

    def test_no_cross_book_contamination(self):
        """Different books should not share character data."""
        profile_a = GraphProfile(
            book_id="book-a",
            character_seeds={"角色A"},
            aliases={"别名A": "角色A"},
        )
        profile_b = GraphProfile(
            book_id="book-b",
            character_seeds={"角色B"},
            aliases={"别名B": "角色B"},
        )
        # Book A's aliases should not work for Book B
        assert resolve_aliases_with_profile("别名A", profile_b) == "别名A"
        assert resolve_aliases_with_profile("别名B", profile_a) == "别名B"

    def test_sample_book_graph_profile_has_expected_data(self):
        """Sample book graph_profile.json should contain expected character data."""
        profile = load_graph_profile("凡人修仙传")
        # Verify key characters from the actual graph_profile.json
        assert "韩立" in profile.character_seeds
        assert "南宫婉" in profile.character_seeds
        assert "墨大夫" in profile.character_seeds
        # Verify key aliases
        assert profile.aliases.get("二愣子") == "韩立"
        assert profile.aliases.get("墨老") == "墨大夫"
        assert profile.aliases.get("三叔") == "韩胖子"
