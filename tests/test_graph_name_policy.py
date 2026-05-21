"""Tests for graph_name_policy three-evidence filtering (US-004) and whitelist (US-006)."""
import json
from pathlib import Path

import pytest

from novel_system.graph_name_policy import (
    CandidateEvidence,
    GraphProfile,
    build_candidate_evidence_from_chapters,
    filter_candidates_with_evidence,
    is_book_in_whitelist,
    get_policy_mode,
    auto_detect_book,
    load_whitelist_config,
    reset_whitelist_config_cache,
    normalize_name_with_profile,
    GRAPH_WHITELIST,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_evidence(freq: int = 1, span: int = 1, scene: bool = False) -> CandidateEvidence:
    return CandidateEvidence(frequency=freq, chapter_span=span, has_scene_evidence=scene)


# ---------------------------------------------------------------------------
# Three-evidence filtering
# ---------------------------------------------------------------------------

class TestFilterCandidatesWithEvidence:

    def test_passes_when_all_three_evidence_present(self):
        """候选同时具备频率、章节跨度、场景证据时应通过。"""
        candidates = {
            "韩立": _make_evidence(freq=10, span=8, scene=True),
        }
        result = filter_candidates_with_evidence(candidates)
        assert len(result) == 1
        assert result[0]["canonical_name"] == "韩立"
        assert result[0]["frequency"] == 10
        assert result[0]["chapter_span"] == 8
        assert result[0]["scene_evidence"] is True

    def test_filters_low_frequency(self):
        """频率低于阈值的候选应被过滤。"""
        candidates = {
            "韩立": _make_evidence(freq=1, span=1, scene=True),
        }
        result = filter_candidates_with_evidence(candidates, min_frequency=2)
        assert len(result) == 0

    def test_filters_low_score(self):
        """综合分数低于阈值的非种子候选应被过滤。"""
        candidates = {
            "路人甲": _make_evidence(freq=2, span=1, scene=False),
        }
        # score = 2*1.0 + 1*2.0 + 0 + 0 = 4.0, above default 3.0
        result = filter_candidates_with_evidence(candidates, min_score=5.0)
        assert len(result) == 0

    def test_seed_names_get_bonus_score(self):
        """种子名应获得额外分数，更容易通过过滤。"""
        profile = GraphProfile(
            book_id="test",
            character_seeds={"韩立"},
        )
        candidates = {
            "韩立": _make_evidence(freq=2, span=1, scene=False),
        }
        # score = 2*1.0 + 1*2.0 + 0 + 5.0(seed) = 9.0
        result = filter_candidates_with_evidence(candidates, profile, min_score=8.0)
        assert len(result) == 1
        assert result[0]["is_seed"] is True

    def test_scene_evidence_adds_score(self):
        """场景证据应增加候选分数。"""
        with_scene = {
            "韩立": _make_evidence(freq=3, span=2, scene=True),
        }
        without_scene = {
            "韩立": _make_evidence(freq=3, span=2, scene=False),
        }
        result_with = filter_candidates_with_evidence(with_scene)
        result_without = filter_candidates_with_evidence(without_scene)
        assert result_with[0]["score"] > result_without[0]["score"]

    def test_chapter_span_contributes_to_score(self):
        """章节跨度应正向影响分数。"""
        wide_span = {
            "韩立": _make_evidence(freq=3, span=10, scene=False),
        }
        narrow_span = {
            "韩立": _make_evidence(freq=3, span=1, scene=False),
        }
        result_wide = filter_candidates_with_evidence(wide_span)
        result_narrow = filter_candidates_with_evidence(narrow_span)
        assert result_wide[0]["score"] > result_narrow[0]["score"]


# ---------------------------------------------------------------------------
# normalize_name_with_profile
# ---------------------------------------------------------------------------

class TestNormalizeNameWithProfile:

    def test_suffix_normalization(self):
        """带后缀的名字应规范化为已知基础名，如 '韩立现' -> '韩立'。"""
        known = {"韩立"}
        assert normalize_name_with_profile("韩立现", known) == "韩立"

    def test_noise_word_returns_none(self):
        """噪声词如 '时间' 应返回 None。"""
        known = {"韩立"}
        assert normalize_name_with_profile("时间", known) is None

    def test_known_name_passes_validation(self):
        """已知名字通过 looks_like_graph_name 验证后应返回自身。"""
        known = {"韩立"}
        assert normalize_name_with_profile("韩立", known) == "韩立"

    def test_noise_in_known_names_rejected(self):
        """混入 known_names 的噪声词应被拒绝，不应绕过验证。"""
        known = {"时间", "韩立"}
        assert normalize_name_with_profile("时间", known) is None

    def test_empty_name_returns_none(self):
        """空字符串或纯空白应返回 None。"""
        assert normalize_name_with_profile("", set()) is None
        assert normalize_name_with_profile("  ", set()) is None

    def test_alias_resolution(self):
        """别名应解析为规范名。"""
        profile = GraphProfile(book_id="test", aliases={"二愣子": "韩立"})
        assert normalize_name_with_profile("二愣子", set(), profile) == "韩立"

    def test_seed_name_returns_self(self):
        """种子名应直接返回自身。"""
        profile = GraphProfile(book_id="test", character_seeds={"韩立"})
        assert normalize_name_with_profile("韩立", set(), profile) == "韩立"

    def test_non_name_returns_none(self):
        """非人名应返回 None。"""
        assert normalize_name_with_profile("的韩", {"韩立"}) is None


# ---------------------------------------------------------------------------
# Determinism / repeatability
# ---------------------------------------------------------------------------

class TestFilterDeterminism:

    def test_same_input_produces_same_output(self):
        """相同输入应产生完全相同的输出（可重复性）。"""
        candidates = {
            "韩立": _make_evidence(freq=10, span=8, scene=True),
            "张铁": _make_evidence(freq=5, span=3, scene=True),
            "墨大夫": _make_evidence(freq=4, span=2, scene=False),
            "路人甲": _make_evidence(freq=2, span=1, scene=False),
        }
        results = []
        for _ in range(5):
            result = filter_candidates_with_evidence(candidates)
            results.append(result)

        for r in results[1:]:
            assert r == results[0]

    def test_output_order_is_stable(self):
        """输出顺序应稳定（按分数降序）。"""
        candidates = {
            "韩立": _make_evidence(freq=10, span=8, scene=True),
            "张铁": _make_evidence(freq=5, span=3, scene=True),
            "墨大夫": _make_evidence(freq=3, span=2, scene=False),
        }
        result = filter_candidates_with_evidence(candidates)
        scores = [r["score"] for r in result]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:

    def test_deduplicates_by_canonical_name(self):
        """同一 canonical name 的多个候选应去重，保留最高分。"""
        candidates = {
            "韩立": _make_evidence(freq=10, span=8, scene=True),
            "二愣子": _make_evidence(freq=3, span=2, scene=False),
        }
        profile = GraphProfile(
            book_id="test",
            aliases={"二愣子": "韩立"},
        )
        result = filter_candidates_with_evidence(candidates, profile)
        # Both normalize to "韩立", should deduplicate
        canonical_names = [r["canonical_name"] for r in result]
        assert canonical_names.count("韩立") == 1


# ---------------------------------------------------------------------------
# build_candidate_evidence_from_chapters
# ---------------------------------------------------------------------------

class TestBuildCandidateEvidence:

    def test_counts_frequency_across_chapters(self):
        """应正确统计跨章节的出现频率。"""
        chapters = [
            {"chapter": 1, "text": "韩立和张铁来到七玄门。"},
            {"chapter": 2, "text": "韩立修炼长春功。"},
            {"chapter": 3, "text": "张铁和韩立切磋。"},
        ]

        def extract(text):
            names = []
            for name in ["韩立", "张铁"]:
                if name in text:
                    names.append(name)
            return names

        evidence = build_candidate_evidence_from_chapters(chapters, extract)

        assert evidence["韩立"].frequency == 3
        assert evidence["张铁"].frequency == 2

    def test_counts_chapter_span(self):
        """应正确统计章节跨度。"""
        chapters = [
            {"chapter": 1, "text": "韩立出现。"},
            {"chapter": 2, "text": "韩立又出现。"},
            {"chapter": 3, "text": "无名氏出现。"},
        ]

        def extract(text):
            if "韩立" in text:
                return ["韩立"]
            if "无名氏" in text:
                return ["无名氏"]
            return []

        evidence = build_candidate_evidence_from_chapters(chapters, extract)

        assert evidence["韩立"].chapter_span == 2
        assert evidence["无名氏"].chapter_span == 1

    def test_empty_chapters_produce_empty_evidence(self):
        """空章节应产生空证据。"""
        evidence = build_candidate_evidence_from_chapters([], lambda t: [])
        assert evidence == {}

    def test_returns_dict_not_defaultdict(self):
        """返回值应为普通 dict，避免意外创建条目。"""
        chapters = [{"chapter": 1, "text": "韩立出现。"}]
        evidence = build_candidate_evidence_from_chapters(
            chapters, lambda t: ["韩立"] if "韩立" in t else []
        )
        assert type(evidence) is dict
        assert "不存在" not in evidence


# ---------------------------------------------------------------------------
# Whitelist configuration (US-006)
# ---------------------------------------------------------------------------


class TestWhitelistHardcoded:
    """Tests for hardcoded GRAPH_WHITELIST set."""

    def test_hardcoded_whitelist_contains_expected_books(self):
        """硬编码白名单应包含预期的书籍。"""
        assert "凡人修仙传" in GRAPH_WHITELIST
        assert "凡人修仙传-1-500章-txt" in GRAPH_WHITELIST

    def test_is_book_in_whitelist_hit(self):
        """白名单中的书籍应返回 True。"""
        assert is_book_in_whitelist("凡人修仙传") is True

    def test_is_book_in_whitelist_miss(self):
        """不在白名单中的书籍应返回 False。"""
        reset_whitelist_config_cache()
        assert is_book_in_whitelist("unknown_book_xyz") is False

    def test_get_policy_mode_profile(self):
        """白名单书籍应返回 'profile' 模式。"""
        assert get_policy_mode("凡人修仙传") == "profile"

    def test_get_policy_mode_heuristic(self):
        """非白名单书籍应返回 'heuristic' 模式。"""
        reset_whitelist_config_cache()
        assert get_policy_mode("unknown_book_xyz") == "heuristic"


class TestWhitelistConfigFile:
    """Tests for external whitelist.json config file."""

    @pytest.fixture(autouse=True)
    def _reset_cache(self):
        """Reset whitelist config cache before each test."""
        reset_whitelist_config_cache()
        yield
        reset_whitelist_config_cache()

    def test_load_config_from_file(self, tmp_path: Path):
        """应能从 whitelist.json 加载配置。"""
        config_data = {"books": ["custom-book-1", "custom-book-2"], "auto_detect": False}
        (tmp_path / "whitelist.json").write_text(
            json.dumps(config_data, ensure_ascii=False), encoding="utf-8"
        )

        result = load_whitelist_config(data_dir=tmp_path)
        assert result["books"] == ["custom-book-1", "custom-book-2"]
        assert result["auto_detect"] is False

    def test_load_config_missing_file_returns_defaults(self, tmp_path: Path):
        """缺少 whitelist.json 时应返回默认配置。"""
        result = load_whitelist_config(data_dir=tmp_path)
        assert result["books"] == []
        assert result["auto_detect"] is True

    def test_load_config_invalid_json_returns_defaults(self, tmp_path: Path):
        """无效 JSON 应返回默认配置。"""
        (tmp_path / "whitelist.json").write_text("{ bad json", encoding="utf-8")

        result = load_whitelist_config(data_dir=tmp_path)
        assert result["books"] == []
        assert result["auto_detect"] is True

    def test_config_file_books_are_whitelisted(self, tmp_path: Path):
        """配置文件中的书籍应被识别为白名单。"""
        config_data = {"books": ["custom-novel"], "auto_detect": False}
        (tmp_path / "whitelist.json").write_text(
            json.dumps(config_data, ensure_ascii=False), encoding="utf-8"
        )

        assert is_book_in_whitelist("custom-novel", data_dir=tmp_path) is True

    def test_config_file_does_not_affect_hardcoded(self, tmp_path: Path):
        """配置文件不应影响硬编码白名单的判定。"""
        config_data = {"books": [], "auto_detect": False}
        (tmp_path / "whitelist.json").write_text(
            json.dumps(config_data, ensure_ascii=False), encoding="utf-8"
        )

        # Hardcoded books still pass even if not in config file
        assert is_book_in_whitelist("凡人修仙传", data_dir=tmp_path) is True


class TestWhitelistAutoDetect:
    """Tests for auto-detection based on graph_profile.json presence."""

    @pytest.fixture(autouse=True)
    def _reset_cache(self):
        """Reset whitelist config cache before each test."""
        reset_whitelist_config_cache()
        yield
        reset_whitelist_config_cache()

    def test_auto_detect_with_profile_json(self, tmp_path: Path):
        """有 graph_profile.json 的书籍应被自动检测。"""
        book_dir = tmp_path / "new-book"
        book_dir.mkdir()
        (book_dir / "graph_profile.json").write_text("{}", encoding="utf-8")

        assert auto_detect_book("new-book", data_dir=tmp_path) is True

    def test_auto_detect_without_profile_json(self, tmp_path: Path):
        """没有 graph_profile.json 的书籍不应被自动检测。"""
        book_dir = tmp_path / "empty-book"
        book_dir.mkdir()

        assert auto_detect_book("empty-book", data_dir=tmp_path) is False

    def test_auto_detect_nonexistent_book(self, tmp_path: Path):
        """不存在的书籍目录不应被自动检测。"""
        assert auto_detect_book("no-such-book", data_dir=tmp_path) is False

    def test_auto_detect_whitelists_book(self, tmp_path: Path):
        """自动检测到的书籍应被加入白名单。"""
        # Create whitelist.json with auto_detect enabled (default)
        config_data = {"books": [], "auto_detect": True}
        (tmp_path / "whitelist.json").write_text(
            json.dumps(config_data, ensure_ascii=False), encoding="utf-8"
        )

        # Create book with graph_profile.json
        books_dir = tmp_path / "books"
        book_dir = books_dir / "auto-book"
        book_dir.mkdir(parents=True)
        (book_dir / "graph_profile.json").write_text("{}", encoding="utf-8")

        assert is_book_in_whitelist("auto-book", data_dir=tmp_path) is True

    def test_auto_detect_disabled_ignores_profile(self, tmp_path: Path):
        """auto_detect=false 时不应自动检测。"""
        config_data = {"books": [], "auto_detect": False}
        (tmp_path / "whitelist.json").write_text(
            json.dumps(config_data, ensure_ascii=False), encoding="utf-8"
        )

        books_dir = tmp_path / "books"
        book_dir = books_dir / "auto-book"
        book_dir.mkdir(parents=True)
        (book_dir / "graph_profile.json").write_text("{}", encoding="utf-8")

        assert is_book_in_whitelist("auto-book", data_dir=tmp_path) is False


class TestWhitelistDeterminism:
    """Tests for whitelist determinism and repeatability."""

    @pytest.fixture(autouse=True)
    def _reset_cache(self):
        reset_whitelist_config_cache()
        yield
        reset_whitelist_config_cache()

    def test_same_input_produces_same_result(self, tmp_path: Path):
        """相同输入应产生相同结果。"""
        config_data = {"books": ["stable-book"], "auto_detect": True}
        (tmp_path / "whitelist.json").write_text(
            json.dumps(config_data, ensure_ascii=False), encoding="utf-8"
        )

        results = [is_book_in_whitelist("stable-book", data_dir=tmp_path) for _ in range(5)]
        assert all(r == results[0] for r in results)

    def test_hit_miss_samples(self, tmp_path: Path):
        """应能区分命中与未命中的样例。"""
        config_data = {"books": ["hit-book"], "auto_detect": False}
        (tmp_path / "whitelist.json").write_text(
            json.dumps(config_data, ensure_ascii=False), encoding="utf-8"
        )

        # Hit
        assert is_book_in_whitelist("hit-book", data_dir=tmp_path) is True
        # Miss
        assert is_book_in_whitelist("miss-book", data_dir=tmp_path) is False
