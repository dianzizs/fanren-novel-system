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
    GRAPH_CANON_SEEDS,
    GRAPH_ALIAS_LOOKUP,
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

    def test_constants_exist_for_documentation_only(self):
        """GRAPH_CANON_SEEDS/GRAPH_ALIAS_LOOKUP exist for documentation only.

        These constants show the migrated values but are NOT used as defaults.
        """
        # Constants still exist (for documentation/reference)
        assert "韩立" in GRAPH_CANON_SEEDS
        assert GRAPH_ALIAS_LOOKUP.get("二愣子") == "韩立"

        # But default profile is empty
        profile = GraphProfile.default()
        assert profile.character_seeds == set()

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
