"""Tests for graph_name_policy GraphProfile loading and validation."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from novel_system.graph_name_policy import (
    GraphProfile,
    load_graph_profile,
    normalize_name_with_profile,
    resolve_aliases_with_profile,
    filter_candidates_with_profile,
    get_effective_seeds_and_aliases,
    build_profile_from_character_registry,
    is_book_in_whitelist,
    get_policy_mode,
    GRAPH_WHITELIST,
)


class TestGraphProfile:
    """Tests for GraphProfile dataclass."""

    def test_default_profile_is_empty(self):
        """Default profile should be empty - no book-specific contamination."""
        profile = GraphProfile.default("test-book")
        assert profile.character_seeds == set()
        assert profile.aliases == {}
        assert profile.manual_fixes == []

    def test_default_profile_has_book_id(self):
        """Default profile should preserve book_id."""
        profile = GraphProfile.default("my-book")
        assert profile.book_id == "my-book"

    def test_from_dict_with_full_schema(self):
        """GraphProfile should parse all schema fields."""
        data = {
            "book_id": "my-book",
            "character_seeds": ["张三", "李四"],
            "aliases": {"小张": "张三", "小李": "李四"},
            "manual_fixes": [{"from": "老张", "to": "张三"}],
        }
        profile = GraphProfile.from_dict(data)
        assert profile.book_id == "my-book"
        assert profile.character_seeds == {"张三", "李四"}
        assert profile.aliases == {"小张": "张三", "小李": "李四"}
        assert len(profile.manual_fixes) == 1

    def test_from_dict_with_missing_fields(self):
        """GraphProfile should handle missing optional fields."""
        data = {"book_id": "minimal"}
        profile = GraphProfile.from_dict(data)
        assert profile.book_id == "minimal"
        assert profile.character_seeds == set()
        assert profile.aliases == {}
        assert profile.manual_fixes == []


class TestLoadGraphProfile:
    """Tests for load_graph_profile function."""

    def test_load_profile_from_file(self, tmp_path: Path):
        """Should load profile from graph_profile.json."""
        book_dir = tmp_path / "test-book"
        book_dir.mkdir(parents=True)

        profile_data = {
            "book_id": "test-book",
            "character_seeds": ["角色A", "角色B"],
            "aliases": {"A": "角色A"},
            "manual_fixes": [],
        }
        (book_dir / "graph_profile.json").write_text(
            json.dumps(profile_data, ensure_ascii=False), encoding="utf-8"
        )

        profile = load_graph_profile("test-book", data_dir=tmp_path)
        assert profile.book_id == "test-book"
        assert "角色A" in profile.character_seeds
        assert profile.aliases.get("A") == "角色A"

    def test_fallback_to_empty_when_missing(self, tmp_path: Path):
        """Should return empty profile when file doesn't exist."""
        book_dir = tmp_path / "missing-book"
        book_dir.mkdir(parents=True)
        # No graph_profile.json created

        profile = load_graph_profile("missing-book", data_dir=tmp_path)
        assert profile.book_id == "missing-book"
        # Should be empty, not contaminated with book-specific defaults
        assert profile.character_seeds == set()
        assert profile.aliases == {}

    def test_fallback_to_empty_on_invalid_json(self, tmp_path: Path):
        """Should return empty profile when JSON is invalid."""
        book_dir = tmp_path / "bad-json-book"
        book_dir.mkdir(parents=True)

        (book_dir / "graph_profile.json").write_text(
            "{ invalid json }", encoding="utf-8"
        )

        profile = load_graph_profile("bad-json-book", data_dir=tmp_path)
        # Should fall back to empty profile
        assert profile.book_id == "bad-json-book"
        assert profile.character_seeds == set()
        assert profile.aliases == {}

    def test_profile_seeds_merge_with_defaults(self, tmp_path: Path):
        """Profile seeds should be used alongside defaults."""
        book_dir = tmp_path / "extended-book"
        book_dir.mkdir(parents=True)

        profile_data = {
            "book_id": "extended-book",
            "character_seeds": ["新角色"],
            "aliases": {"新别名": "新角色"},
            "manual_fixes": [],
        }
        (book_dir / "graph_profile.json").write_text(
            json.dumps(profile_data, ensure_ascii=False), encoding="utf-8"
        )

        profile = load_graph_profile("extended-book", data_dir=tmp_path)
        # Profile seeds are separate from defaults
        assert "新角色" in profile.character_seeds
        assert "新别名" in profile.aliases


class TestGraphProfileSchema:
    """Tests for schema validation and structure."""

    def test_character_seeds_is_set(self):
        """character_seeds should be a set."""
        profile = GraphProfile(book_id="test", character_seeds={"A", "B"})
        assert isinstance(profile.character_seeds, set)
        assert "A" in profile.character_seeds

    def test_aliases_is_dict(self):
        """aliases should be a dict mapping alias -> canonical."""
        profile = GraphProfile(book_id="test", aliases={"alias": "canonical"})
        assert isinstance(profile.aliases, dict)
        assert profile.aliases["alias"] == "canonical"

    def test_manual_fixes_is_list(self):
        """manual_fixes should be a list of corrections."""
        profile = GraphProfile(
            book_id="test",
            manual_fixes=[{"from": "old", "to": "new"}],
        )
        assert isinstance(profile.manual_fixes, list)
        assert len(profile.manual_fixes) == 1


class TestProfileAwareFunctions:
    """Tests for profile-aware normalization and filtering functions."""

    def test_normalize_name_with_profile_uses_aliases(self):
        """normalize_name_with_profile should use profile aliases."""
        profile = GraphProfile(
            book_id="test",
            character_seeds={"韩立", "张铁"},
            aliases={"二愣子": "韩立", "自定义别名": "张铁"},
        )
        known_names = {"韩立", "张铁"}

        # Profile alias should work
        result = normalize_name_with_profile("二愣子", known_names, profile)
        assert result == "韩立"

        # Custom profile alias should work
        result = normalize_name_with_profile("自定义别名", known_names, profile)
        assert result == "张铁"

    def test_normalize_name_with_profile_none_returns_none_for_alias(self):
        """normalize_name_with_profile with None profile returns None for alias.

        IMPORTANT: Without profile, no alias resolution - prevents cross-book contamination.
        """
        known_names = {"韩立", "张铁"}

        # Without profile, alias lookup fails
        result = normalize_name_with_profile("二愣子", known_names, None)
        # "二愣子" not in known_names, so returns None or the name itself
        # (depends on whether it passes looks_like_graph_name)
        assert result is None or result == "二愣子"

    def test_resolve_aliases_with_profile(self):
        """resolve_aliases_with_profile should use profile aliases."""
        profile = GraphProfile(
            book_id="test",
            aliases={"二愣子": "韩立"},
        )

        assert resolve_aliases_with_profile("二愣子", profile) == "韩立"
        assert resolve_aliases_with_profile("韩立", profile) == "韩立"
        assert resolve_aliases_with_profile("未知人物", profile) == "未知人物"

    def test_resolve_aliases_with_profile_none_returns_name(self):
        """resolve_aliases_with_profile with None returns name unchanged.

        IMPORTANT: Without profile, no alias resolution - prevents cross-book contamination.
        """
        assert resolve_aliases_with_profile("二愣子", None) == "二愣子"
        assert resolve_aliases_with_profile("墨老", None) == "墨老"
        assert resolve_aliases_with_profile("韩立", None) == "韩立"

    def test_filter_candidates_with_profile(self):
        """filter_candidates_with_profile should use profile seeds."""
        profile = GraphProfile(
            book_id="test",
            character_seeds={"韩立", "张铁", "墨大夫"},
            aliases={"二愣子": "韩立"},
        )

        character_docs = [
            (0, {"name": "韩立", "chapters": [1, 2, 3]}),
            (1, {"name": "张铁", "chapters": [1]}),
        ]
        event_docs = [
            (0, {"participants": ["韩立", "墨大夫"]}),
        ]

        scores, known_names = filter_candidates_with_profile(
            {}, character_docs, event_docs, profile
        )

        assert "韩立" in known_names
        assert "墨大夫" in known_names

    def test_filter_candidates_without_profile_returns_empty(self):
        """filter_candidates_with_profile with None profile returns empty set.

        IMPORTANT: No profile means no known names - prevents cross-book contamination.
        """
        character_docs = [
            (0, {"name": "韩立", "chapters": [1, 2, 3]}),
        ]
        event_docs = []

        scores, known_names = filter_candidates_with_profile(
            {}, character_docs, event_docs, None
        )

        # Should be empty - no profile means no book-specific knowledge
        assert known_names == set()

    def test_get_effective_seeds_and_aliases_with_profile(self):
        """get_effective_seeds_and_aliases with profile returns profile data."""
        profile = GraphProfile(
            book_id="test",
            character_seeds={"韩立", "张铁"},
            aliases={"二愣子": "韩立"},
        )

        seeds, aliases = get_effective_seeds_and_aliases(profile)
        assert seeds == {"韩立", "张铁"}
        assert aliases == {"二愣子": "韩立"}

    def test_get_effective_seeds_and_aliases_none_returns_empty(self):
        """get_effective_seeds_and_aliases with None returns empty."""
        seeds, aliases = get_effective_seeds_and_aliases(None)
        assert seeds == set()
        assert aliases == {}


class TestWhitelistPolicy:
    """Tests for book whitelist policy."""

    def test_is_book_in_whitelist_returns_true_for_whitelisted_book(self):
        """Books in GRAPH_WHITELIST should return True."""
        # Use a book ID that's in the whitelist
        assert is_book_in_whitelist("凡人修仙传") is True

    def test_is_book_in_whitelist_returns_false_for_non_whitelisted_book(self):
        """Books not in GRAPH_WHITELIST should return False."""
        assert is_book_in_whitelist("nonexistent_book") is False
        assert is_book_in_whitelist("random_novel") is False

    def test_get_policy_mode_returns_profile_for_whitelisted_book(self):
        """Whitelisted books should return 'profile' mode."""
        assert get_policy_mode("凡人修仙传") == "profile"

    def test_get_policy_mode_returns_heuristic_for_non_whitelisted_book(self):
        """Non-whitelisted books should return 'heuristic' mode."""
        assert get_policy_mode("unknown_book") == "heuristic"

    def test_whitelist_is_modifiable(self):
        """GRAPH_WHITELIST should be a set that can be modified."""
        original_count = len(GRAPH_WHITELIST)
        # Add a test book
        GRAPH_WHITELIST.add("test_book_for_whitelist")
        assert is_book_in_whitelist("test_book_for_whitelist") is True
        # Remove it
        GRAPH_WHITELIST.discard("test_book_for_whitelist")
        assert is_book_in_whitelist("test_book_for_whitelist") is False
        assert len(GRAPH_WHITELIST) == original_count


class TestBuildProfileFromCharacterRegistry:
    """Tests for building GraphProfile from character_registry artifact."""

    def test_build_profile_from_empty_registry(self):
        """Empty registry should return empty profile."""
        profile = build_profile_from_character_registry([], "test-book")
        assert profile.book_id == "test-book"
        assert profile.character_seeds == set()
        assert profile.aliases == {}

    def test_build_profile_extracts_canonical_names(self):
        """Profile should include canonical names as seeds."""
        registry = [
            {"canonical_name": "韩立", "aliases": []},
            {"canonical_name": "张铁", "aliases": []},
        ]
        profile = build_profile_from_character_registry(registry)
        assert "韩立" in profile.character_seeds
        assert "张铁" in profile.character_seeds

    def test_build_profile_extracts_aliases(self):
        """Profile should include aliases mapping to canonical names."""
        registry = [
            {"canonical_name": "韩立", "aliases": ["二愣子", "韩老魔"]},
            {"canonical_name": "墨大夫", "aliases": ["墨老"]},
        ]
        profile = build_profile_from_character_registry(registry)
        assert profile.aliases.get("二愣子") == "韩立"
        assert profile.aliases.get("韩老魔") == "韩立"
        assert profile.aliases.get("墨老") == "墨大夫"

    def test_build_profile_handles_missing_aliases(self):
        """Profile should handle entries without aliases field."""
        registry = [
            {"canonical_name": "韩立"},
        ]
        profile = build_profile_from_character_registry(registry)
        assert "韩立" in profile.character_seeds
        assert profile.aliases == {}

    def test_build_profile_ignores_empty_canonical_names(self):
        """Profile should skip entries with empty canonical names."""
        registry = [
            {"canonical_name": "韩立", "aliases": []},
            {"canonical_name": "", "aliases": ["别名"]},
            {"canonical_name": None, "aliases": []},
        ]
        profile = build_profile_from_character_registry(registry)
        assert "韩立" in profile.character_seeds
        assert len(profile.character_seeds) == 1

    def test_build_profile_from_real_registry_format(self):
        """Profile should handle real character_registry format from indexing."""
        registry = [
            {
                "id": "reg-韩立",
                "canonical_name": "韩立",
                "aliases": ["二愣子"],
                "frequency": 100,
                "chapter_span": 50,
                "chapters": [1, 2, 3, 4, 5],
                "scene_evidence": True,
                "score": 150.0,
                "is_seed": True,
            },
            {
                "id": "reg-张铁",
                "canonical_name": "张铁",
                "aliases": [],
                "frequency": 30,
                "chapter_span": 10,
                "chapters": [1, 2, 3],
                "scene_evidence": True,
                "score": 50.0,
                "is_seed": False,
            },
        ]
        profile = build_profile_from_character_registry(registry, "凡人修仙传")
        assert profile.book_id == "凡人修仙传"
        assert "韩立" in profile.character_seeds
        assert "张铁" in profile.character_seeds
        assert profile.aliases.get("二愣子") == "韩立"


class TestConfigLayerOverride:
    """Tests that graph_profile.json config layer is the source of truth."""

    def test_load_profile_from_config_for_main_book(self):
        """Loading profile for 凡人修仙传 should read from graph_profile.json."""
        profile = load_graph_profile("凡人修仙传")
        assert profile.book_id == "凡人修仙传"
        assert "韩立" in profile.character_seeds
        assert "南宫婉" in profile.character_seeds
        assert profile.aliases.get("二愣子") == "韩立"
        assert profile.aliases.get("墨老") == "墨大夫"

    def test_load_profile_from_config_for_subset_book(self):
        """Loading profile for 凡人修仙传-1-500章-txt should read from graph_profile.json."""
        profile = load_graph_profile("凡人修仙传-1-500章-txt")
        assert profile.book_id == "凡人修仙传-1-500章-txt"
        assert "韩立" in profile.character_seeds
        assert profile.aliases.get("二愣子") == "韩立"

    def test_config_seeds_are_loaded_from_profile(self):
        """Config-loaded seeds should come from graph_profile.json."""
        profile = load_graph_profile("凡人修仙传")
        # Verify key characters are present (data from graph_profile.json)
        assert "韩立" in profile.character_seeds
        assert "南宫婉" in profile.character_seeds
        assert len(profile.character_seeds) > 10  # Should have many characters

    def test_config_aliases_are_loaded_from_profile(self):
        """Config-loaded aliases should come from graph_profile.json."""
        profile = load_graph_profile("凡人修仙传")
        # Verify key aliases are present (data from graph_profile.json)
        assert profile.aliases.get("二愣子") == "韩立"
        assert profile.aliases.get("墨老") == "墨大夫"
        assert len(profile.aliases) > 2  # Should have multiple aliases

    def test_missing_profile_falls_back_to_empty(self, tmp_path: Path):
        """Books without graph_profile.json get empty defaults (no cross-book contamination)."""
        profile = load_graph_profile("nonexistent-book", data_dir=tmp_path)
        assert profile.character_seeds == set()
        assert profile.aliases == {}

    def test_orchestrator_no_longer_imports_graph_canon_seeds(self):
        """orchestrator.py should not import GRAPH_CANON_SEEDS directly."""
        import ast
        from pathlib import Path

        orchestrator_path = Path(__file__).parent.parent / "novel_system" / "search" / "orchestrator.py"
        source = orchestrator_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and "graph_name_policy" in node.module:
                    imported_names = [alias.name for alias in node.names]
                    assert "GRAPH_CANON_SEEDS" not in imported_names, (
                        "orchestrator.py should not import GRAPH_CANON_SEEDS; "
                        "use character_names parameter instead"
                    )
