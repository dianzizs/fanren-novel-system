from __future__ import annotations

from .models import LoadedBookIndex, scope_filter
from .repository import BookIndexRepository
from .artifact_builders import (
    build_event_timeline,
    build_character_cards,
    build_book_artifacts,
)
from .scene import (
    FilterThresholds,
    CharacterRegistryBuilder,
    SceneSegmentBuilder,
    build_chapter_chunks,
)
from .constants import (
    CHAPTER_RE,
    SENTENCE_RE,
    COMMON_SURNAMES,
    PERSON_RE,
    TITLE_PERSON_RE,
    ORG_RE,
    STOP_NAMES,
    BAD_NAME_ENDINGS,
    RULE_PATTERNS,
    LOCATION_SHIFT_RE,
)

__all__ = [
    "BookIndexRepository",
    "LoadedBookIndex",
    "scope_filter",
    "build_event_timeline",
    "build_character_cards",
    "build_book_artifacts",
    "FilterThresholds",
    "CharacterRegistryBuilder",
    "SceneSegmentBuilder",
    "build_chapter_chunks",
    "CHAPTER_RE",
    "SENTENCE_RE",
    "COMMON_SURNAMES",
    "PERSON_RE",
    "TITLE_PERSON_RE",
    "ORG_RE",
    "STOP_NAMES",
    "BAD_NAME_ENDINGS",
    "RULE_PATTERNS",
    "LOCATION_SHIFT_RE",
]
