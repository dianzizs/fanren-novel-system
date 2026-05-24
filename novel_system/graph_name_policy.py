"""Unified graph character naming policy.

Single source of truth for character name normalization, alias resolution,
and candidate filtering across the graph pipeline.

Supports per-book configuration via graph_profile.json files.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .indexing.constants import COMMON_SURNAMES

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GRAPH_TITLE_SUFFIXES = (
    "大夫", "护法", "堂主", "门主", "师兄", "师姐", "师弟", "师父",
    "长老", "掌柜", "胖子", "师叔", "师伯", "仙子", "上人",
)


GRAPH_GENERIC_NAMES = {
    "时间", "方法", "武功", "石室", "山崖", "麻绳", "童子", "章完",
    "储物袋", "平安符", "成了一", "成功", "家伙", "麻烦", "解释道",
    "顾不得", "许多", "段时间", "明白", "符箓", "高兴", "平静",
    "颜色", "章节", "时分", "万分", "舒服", "计划", "范围", "郁闷",
    "黄龙丹", "张均", "张哥", "许能打", "谈虎色", "解决掉", "陈旧",
    "成了两", "和自己", "和一位", "和普通", "和一个", "和对方",
    "和他们",
}

GRAPH_GENERIC_SUBSTRINGS = {
    "幺", "只能", "的韩", "自己", "一位", "一个", "普通", "对方", "他们",
}

GRAPH_BAD_START_CHARS = {"和", "时", "家", "路", "应", "经", "成"}

GRAPH_BAD_END_CHARS = {"丹", "功", "液", "瓶", "符", "诀", "散", "丸", "草", "药"}

GRAPH_GENERIC_FRAGMENT_CHARS = set(
    "一二三四五六七八九十这那他她你我它的了着过吧吗呢啊呀和与及并就才又也还再已曾在到去来把被让给从向"
    "上下前后里外中内头脸眼手脚身口声步心看听说想觉有见没对同跟于处地天年月日次边面等走修体虽而自"
    "望终大皱只倒站微正用刚神可听看脸身手眼眉脚口面并此再却仍将其惊略知吃为以感现当早无"
)


# ---------------------------------------------------------------------------
# Whitelist configuration for book-specific policy
# ---------------------------------------------------------------------------

# Books in this whitelist use the new graph profile-based naming strategy.
# Books not in the whitelist fall back to default heuristics.
GRAPH_WHITELIST: set[str] = {
    "凡人修仙传",
    "凡人修仙传-1-500章-txt",
}

# Cache for loaded whitelist config
_whitelist_config_cache: dict[str, Any] | None = None
_whitelist_config_loaded: bool = False


def load_whitelist_config(data_dir: Path | None = None) -> dict[str, Any]:
    """Load whitelist configuration from external JSON file.

    Config file format (data/whitelist.json):
    {
        "books": ["book_id_1", "book_id_2"],
        "auto_detect": true
    }

    Args:
        data_dir: Base data directory (defaults to data/)

    Returns:
        Config dict with 'books' (list) and 'auto_detect' (bool)
    """
    global _whitelist_config_cache, _whitelist_config_loaded

    if _whitelist_config_loaded:
        return _whitelist_config_cache  # type: ignore[return-value]

    if data_dir is None:
        from .config import AppConfig
        config = AppConfig.load()
        data_dir = config.data_dir

    config_path = data_dir / "whitelist.json"

    default_config: dict[str, Any] = {"books": [], "auto_detect": True}

    if not config_path.exists():
        logger.debug(f"No whitelist.json found at {config_path}, using defaults")
        _whitelist_config_cache = default_config
        _whitelist_config_loaded = True
        return default_config

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        result: dict[str, Any] = {
            "books": list(data.get("books", [])),
            "auto_detect": bool(data.get("auto_detect", True)),
        }
        logger.info(f"Loaded whitelist config from {config_path}: {len(result['books'])} books, auto_detect={result['auto_detect']}")
        _whitelist_config_cache = result
        _whitelist_config_loaded = True
        return result
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning(f"Failed to load whitelist config from {config_path}: {e}, using defaults")
        _whitelist_config_cache = default_config
        _whitelist_config_loaded = True
        return default_config


def reset_whitelist_config_cache() -> None:
    """Reset the whitelist config cache. Used for testing."""
    global _whitelist_config_cache, _whitelist_config_loaded
    _whitelist_config_cache = None
    _whitelist_config_loaded = False


def auto_detect_book(book_id: str, data_dir: Path | None = None) -> bool:
    """Auto-detect if a book should be whitelisted based on graph_profile.json presence.

    A book with graph_profile.json is considered ready for profile-based policy.

    Args:
        book_id: The book identifier
        data_dir: Base data directory (defaults to data/books)

    Returns:
        True if the book has graph_profile.json, False otherwise
    """
    if data_dir is None:
        from .config import AppConfig
        config = AppConfig.load()
        data_dir = config.data_dir / "books"

    profile_path = data_dir / book_id / "graph_profile.json"
    detected = profile_path.exists()

    if detected:
        logger.info(f"Auto-detected book '{book_id}': graph_profile.json found at {profile_path}")
    else:
        logger.debug(f"Auto-detect for book '{book_id}': no graph_profile.json found")

    return detected


def is_book_in_whitelist(book_id: str, data_dir: Path | None = None) -> bool:
    """Check if a book is in the graph policy whitelist.

    Whitelist sources (in priority order):
    1. Hardcoded GRAPH_WHITELIST set
    2. External whitelist.json config file
    3. Auto-detection: book has graph_profile.json (if auto_detect enabled)

    Books in the whitelist use the new graph profile-based naming strategy.
    Books not in the whitelist fall back to default heuristics.

    Args:
        book_id: The book identifier to check
        data_dir: Base data directory for config loading

    Returns:
        True if the book is in the whitelist, False otherwise
    """
    # Check hardcoded whitelist first
    if book_id in GRAPH_WHITELIST:
        logger.info(f"Whitelist check for book '{book_id}': HIT (hardcoded)")
        return True

    # Check external config
    config = load_whitelist_config(data_dir=data_dir)
    if book_id in config.get("books", []):
        logger.info(f"Whitelist check for book '{book_id}': HIT (config file)")
        return True

    # Check auto-detection
    if config.get("auto_detect", True):
        books_dir: Path | None = None
        if data_dir is not None:
            books_dir = data_dir / "books"
        if auto_detect_book(book_id, data_dir=books_dir):
            logger.info(f"Whitelist check for book '{book_id}': HIT (auto-detected)")
            return True

    logger.info(f"Whitelist check for book '{book_id}': MISS")
    return False


def get_policy_mode(book_id: str) -> str:
    """Get the policy mode for a book based on whitelist status.

    Args:
        book_id: The book identifier

    Returns:
        'profile' if book is in whitelist, 'heuristic' otherwise
    """
    return "profile" if is_book_in_whitelist(book_id) else "heuristic"


# ---------------------------------------------------------------------------
# Graph Profile (per-book configuration)
# ---------------------------------------------------------------------------

@dataclass
class CandidateEvidence:
    """Evidence for a character candidate, used by three-evidence filtering.

    Attributes:
        frequency: How often the name appears across the book
        chapter_span: Number of distinct chapters the name appears in
        has_scene_evidence: Whether the name appears in event/scene contexts
    """
    frequency: int = 0
    chapter_span: int = 0
    has_scene_evidence: bool = False


@dataclass
class GraphProfile:
    """Per-book graph configuration loaded from graph_profile.json.

    Attributes:
        book_id: The book identifier
        character_seeds: Known character names to seed the graph
        aliases: Mapping from alias -> canonical name
        manual_fixes: Manual corrections to apply
    """
    book_id: str
    character_seeds: set[str] = field(default_factory=set)
    aliases: dict[str, str] = field(default_factory=dict)
    manual_fixes: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GraphProfile":
        """Create GraphProfile from parsed JSON dict."""
        return cls(
            book_id=data.get("book_id", ""),
            character_seeds=set(data.get("character_seeds", [])),
            aliases=data.get("aliases", {}),
            manual_fixes=data.get("manual_fixes", []),
        )

    @classmethod
    def default(cls, book_id: str = "") -> "GraphProfile":
        """Create default profile with empty configuration.

        IMPORTANT: Default profile is intentionally empty.
        All character data should come from:
        1. graph_profile.json (explicit per-book config)
        2. character_registry artifact (from indexing)
        """
        return cls(
            book_id=book_id,
            character_seeds=set(),
            aliases={},
            manual_fixes=[],
        )


def load_graph_profile(book_id: str, data_dir: Path | None = None) -> GraphProfile:
    """Load graph profile for a book, with fallback to defaults.

    Args:
        book_id: The book identifier
        data_dir: Base data directory (defaults to data/books)

    Returns:
        GraphProfile with either loaded or default configuration
    """
    if data_dir is None:
        # Default data directory
        from .config import AppConfig
        config = AppConfig.load()
        data_dir = config.data_dir / "books"

    profile_path = data_dir / book_id / "graph_profile.json"

    if not profile_path.exists():
        logger.debug(f"No graph_profile.json found for book {book_id}, using defaults")
        return GraphProfile.default(book_id)

    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        profile = GraphProfile.from_dict(data)
        logger.info(f"Loaded graph profile for book {book_id} from {profile_path}")
        return profile
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning(f"Failed to load graph profile for book {book_id}: {e}, using defaults")
        return GraphProfile.default(book_id)

# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def normalize_name(raw_name: str, known_names: set[str]) -> str | None:
    """Canonicalize a raw character name into its standard form.

    Delegates to normalize_name_with_profile with None profile (uses defaults).
    Returns *None* if the name should be discarded.
    """
    return normalize_name_with_profile(raw_name, known_names, profile=None)


def resolve_aliases(name: str) -> str:
    """Return the canonical name for *name*, or *name* itself if no alias mapping exists.

    Delegates to resolve_aliases_with_profile with None profile (uses defaults).
    """
    return resolve_aliases_with_profile(name, profile=None)


def merge_aliases(*sources: dict[str, list[str]]) -> dict[str, str]:
    """Merge multiple alias sources into a single {alias: canonical} lookup.

    Each source uses the ``{canonical: [alias, ...]}`` format (like ALIAS_MAP).
    Returns a flat ``{alias: canonical}`` dict suitable for resolve_aliases_with_profile.
    Later sources override earlier ones for the same alias.
    """
    merged: dict[str, str] = {}
    for source in sources:
        for canonical, aliases in source.items():
            for alias in aliases:
                merged[alias] = canonical
    return merged


def filter_candidates(
    raw_scores: dict[str, float],
    character_docs: list[tuple[int, dict[str, Any]]],
    event_docs: list[tuple[int, dict[str, Any]]],
) -> tuple[dict[str, float], set[str]]:
    """Build name scores and the known-names seed set.

    Delegates to filter_candidates_with_profile with None profile (uses defaults).
    Returns ``(scores, known_names)`` — everything callers need before
    calling :func:`normalize_name`.
    """
    return filter_candidates_with_profile(raw_scores, character_docs, event_docs, profile=None)


def looks_like_graph_name(name: str) -> bool:
    """Heuristic: does *name* plausibly represent a character?

    This function applies GENERIC heuristics only - no book-specific knowledge.
    Book-specific character validation should be done by checking against profile.
    """
    if not name or name in GRAPH_GENERIC_NAMES:
        return False
    if any(fragment in name for fragment in GRAPH_GENERIC_SUBSTRINGS):
        return False
    # Removed: book-specific constant checks (GRAPH_CANON_SEEDS, ALIAS_MAP, GRAPH_ALIAS_LOOKUP)
    # These caused cross-book contamination. Use profile-based validation instead.
    if any(name.endswith(suffix) for suffix in GRAPH_TITLE_SUFFIXES):
        return True
    if len(name) < 2 or len(name) > 4:
        return False
    if _is_generic_graph_fragment(name):
        return False
    if name[0] in GRAPH_BAD_START_CHARS:
        return False
    if name[0] not in COMMON_SURNAMES:
        return False
    if len(name) >= 3 and any(
        char in GRAPH_GENERIC_FRAGMENT_CHARS for char in name[1:-1]
    ):
        return False
    if len(name) == 2 and name[1] in GRAPH_GENERIC_FRAGMENT_CHARS.union(
        {"子", "氏", "们", "个"}
    ):
        return False
    if name[-1] in GRAPH_BAD_END_CHARS:
        return False
    if name[-1] in GRAPH_GENERIC_FRAGMENT_CHARS:
        return False
    return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_generic_graph_fragment(fragment: str) -> bool:
    if not fragment:
        return True
    return all(char in GRAPH_GENERIC_FRAGMENT_CHARS for char in fragment)


def _build_graph_name_scores(
    character_docs: list[tuple[int, dict[str, Any]]],
    event_docs: list[tuple[int, dict[str, Any]]],
) -> dict[str, float]:
    scores: dict[str, float] = defaultdict(float)
    for _, doc in character_docs:
        scores[str(doc.get("name", ""))] += 1 + min(len(doc.get("chapters", [])) / 8, 3)
    for _, doc in event_docs:
        for participant in doc.get("participants", []):
            scores[str(participant)] += 1.2
    return scores


def _seed_graph_known_names(raw_scores: dict[str, float], profile: GraphProfile | None = None) -> set[str]:
    """Seed known names from profile only.

    IMPORTANT: This function uses ONLY the provided profile data.
    No global/fallback constants are used to prevent cross-book contamination.
    """
    if profile is not None:
        canon_seeds = profile.character_seeds
        alias_lookup = profile.aliases
    else:
        # No profile means no known names - caller must provide profile
        logger.warning("_seed_graph_known_names called without profile - returning empty set")
        return set()

    known = set(canon_seeds)
    known.update(alias_lookup.values())
    short_names: set[str] = set()
    for name, score in raw_scores.items():
        if score < 2 and name not in canon_seeds:
            continue
        if any(name.endswith(suffix) for suffix in GRAPH_TITLE_SUFFIXES):
            known.add(name)
            continue
        if len(name) == 2 and looks_like_graph_name(name):
            short_names.add(name)
            known.add(name)
    for name, score in raw_scores.items():
        if (score < 2 and name not in canon_seeds) or name in known:
            continue
        if not looks_like_graph_name(name):
            continue
        if (
            name not in canon_seeds
            and len(name) in {3, 4}
            and any(
                name.startswith(base) or name.endswith(base) for base in short_names
            )
        ):
            continue
        known.add(name)
    return known


# ---------------------------------------------------------------------------
# Profile-aware public functions
# ---------------------------------------------------------------------------


def normalize_name_with_profile(
    raw_name: str,
    known_names: set[str],
    profile: GraphProfile | None = None,
) -> str | None:
    """Canonicalize a raw character name using a profile.

    Args:
        raw_name: The raw name to normalize
        known_names: Set of known character names
        profile: Optional GraphProfile for book-specific rules

    Returns:
        Canonical name or None if should be discarded

    IMPORTANT: When profile is None, no book-specific alias/seed lookup is done.
    This prevents cross-book contamination.
    """
    if profile is not None:
        alias_lookup = profile.aliases
        canon_seeds = profile.character_seeds
    else:
        # No profile means no book-specific knowledge
        alias_lookup = {}
        canon_seeds = set()

    name = raw_name.strip()
    if not name:
        return None
    if name in alias_lookup:
        return alias_lookup[name]
    if name in canon_seeds:
        return name
    if name in known_names and looks_like_graph_name(name):
        return name

    sorted_known = sorted(known_names, key=len, reverse=True)
    for base in sorted_known:
        if not base:
            continue
        if len(name) > len(base) and name.startswith(base) and (
            len(name) == len(base) + 1
            or _is_generic_graph_fragment(name[len(base):])
        ):
            return base
        if len(name) > len(base) and name.endswith(base) and (
            len(name) == len(base) + 1
            or _is_generic_graph_fragment(name[: -len(base)])
        ):
            return base

    if looks_like_graph_name(name):
        return name
    return None


def resolve_aliases_with_profile(name: str, profile: GraphProfile | None = None) -> str:
    """Resolve alias using profile or return name unchanged.

    IMPORTANT: When profile is None, returns name unchanged - no book-specific lookup.
    This prevents cross-book contamination.
    """
    if profile is not None:
        return profile.aliases.get(name, name)
    return name


def filter_candidates_with_profile(
    raw_scores: dict[str, float],
    character_docs: list[tuple[int, dict[str, Any]]],
    event_docs: list[tuple[int, dict[str, Any]]],
    profile: GraphProfile | None = None,
) -> tuple[dict[str, float], set[str]]:
    """Build name scores and known-names using profile.

    Args:
        raw_scores: Pre-computed name scores (optional, will be computed if empty)
        character_docs: Character card documents
        event_docs: Event timeline documents
        profile: Optional GraphProfile for book-specific rules

    Returns:
        Tuple of (scores, known_names)
    """
    if not raw_scores:
        scores = _build_graph_name_scores(character_docs, event_docs)
    else:
        scores = raw_scores
    known_names = _seed_graph_known_names(scores, profile)
    return scores, known_names


def build_candidate_evidence_from_chapters(
    chapters: list[dict[str, Any]],
    extract_names: Any,
) -> dict[str, CandidateEvidence]:
    """Build CandidateEvidence from chapter data.

    Computes frequency and chapter_span. Scene evidence must be set
    separately by the caller (e.g. by checking character_card or event data).

    Args:
        chapters: List of chapter dicts with 'chapter' and 'text' keys
        extract_names: Callable that extracts person names from text

    Returns:
        Mapping from name to CandidateEvidence
    """
    evidence: dict[str, CandidateEvidence] = {}

    for chapter in chapters:
        text = chapter.get("text", "")
        if not text:
            continue
        names = extract_names(text)
        seen_in_chapter: set[str] = set()
        for name in names:
            if name not in evidence:
                evidence[name] = CandidateEvidence()
            evidence[name].frequency += 1
            if name not in seen_in_chapter:
                evidence[name].chapter_span += 1
                seen_in_chapter.add(name)

    return evidence


def filter_candidates_with_evidence(
    candidates: dict[str, CandidateEvidence],
    profile: GraphProfile | None = None,
    *,
    min_frequency: int = 2,
    min_chapter_span: int = 1,
    min_score: float = 3.0,
) -> list[dict[str, Any]]:
    """Filter character candidates using three-evidence strategy.

    Evidence types:
    - frequency: how often the name appears (noise filter)
    - chapter_span: how many chapters the name appears in (persistence)
    - scene_evidence: whether the name appears in event/scene contexts (relevance)

    Args:
        candidates: Mapping from name to its evidence
        profile: Optional GraphProfile for seed/alias data
        min_frequency: Minimum frequency threshold (default 2)
        min_chapter_span: Minimum chapter span threshold (default 1)
        min_score: Minimum composite score for non-seed names (default 3.0)

    Returns:
        List of filtered candidate dicts, sorted by score descending, deduplicated by canonical name.
        Each dict contains: canonical_name, aliases, frequency, chapter_span, chapters,
        scene_evidence, score, is_seed.
    """
    canon_seeds, alias_lookup = get_effective_seeds_and_aliases(profile)
    known_names = {name for name in candidates if looks_like_graph_name(name)} | canon_seeds

    filtered: list[dict[str, Any]] = []
    for name, evidence in candidates.items():
        if evidence.frequency < min_frequency:
            continue

        normalized = normalize_name_with_profile(name, known_names, profile)
        if not normalized:
            continue

        chapter_span = evidence.chapter_span
        score = (
            evidence.frequency * 1.0
            + chapter_span * 2.0
            + (1.5 if evidence.has_scene_evidence else 0.0)
            + (5.0 if name in canon_seeds else 0.0)
        )

        if score < min_score and name not in canon_seeds:
            continue

        # Collect aliases for this canonical name
        aliases: set[str] = set()
        for alias, canonical in alias_lookup.items():
            if canonical == normalized:
                aliases.add(alias)

        filtered.append({
            "canonical_name": normalized,
            "aliases": sorted(aliases),
            "frequency": evidence.frequency,
            "chapter_span": chapter_span,
            "scene_evidence": evidence.has_scene_evidence,
            "score": round(score, 2),
            "is_seed": name in canon_seeds,
        })

    # Deduplicate by canonical name, keeping highest score
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in sorted(filtered, key=lambda x: -x["score"]):
        canonical = item["canonical_name"]
        if canonical not in seen:
            seen.add(canonical)
            result.append(item)

    return result


def get_effective_seeds_and_aliases(profile: GraphProfile | None = None) -> tuple[set[str], dict[str, str]]:
    """Get effective character seeds and aliases from profile.

    Args:
        profile: Optional GraphProfile

    Returns:
        Tuple of (character_seeds, aliases)

    IMPORTANT: When profile is None, returns empty sets - no book-specific defaults.
    This prevents cross-book contamination.
    """
    if profile is not None:
        return profile.character_seeds, profile.aliases
    return set(), {}


def build_profile_from_character_registry(
    character_registry: list[dict[str, Any]],
    book_id: str = "",
) -> GraphProfile:
    """Build GraphProfile from character_registry artifact.

    This is the standard way to create a profile from indexed artifacts,
    enabling graph to consume only standard artifacts.

    Args:
        character_registry: List of character registry entries from indexing
        book_id: Optional book identifier

    Returns:
        GraphProfile with seeds and aliases extracted from registry
    """
    character_seeds: set[str] = set()
    aliases: dict[str, str] = {}

    for entry in character_registry:
        canonical = entry.get("canonical_name", "")
        if not canonical:
            continue

        # Add canonical name to seeds
        character_seeds.add(canonical)

        # Add aliases from registry entry
        for alias in entry.get("aliases", []):
            if alias and alias != canonical:
                aliases[alias] = canonical

    return GraphProfile(
        book_id=book_id,
        character_seeds=character_seeds,
        aliases=aliases,
        manual_fixes=[],
    )
