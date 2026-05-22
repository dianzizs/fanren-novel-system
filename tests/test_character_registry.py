"""Tests for character registry building."""
from novel_system.indexing import CharacterRegistryBuilder, FilterThresholds


def test_registry_merges_alias_into_canonical_name():
    """角色注册表应将别名合并到规范名称。"""
    scenes = [
        {
            "id": "ch1-scene0",
            "chapter": 1,
            "text": "韩立被村里人叫作二愣子。",
            "major_characters": ["韩立", "二愣子"],
            "raw_character_mentions": ["韩立", "二愣子", "韩立"],
        }
    ]

    registry = CharacterRegistryBuilder(seed_aliases={"韩立": ["二愣子"]}).build(scenes)

    assert len(registry) == 1
    assert registry[0]["canonical_name"] == "韩立"
    assert "二愣子" in registry[0]["aliases"]


def test_registry_tracks_active_range():
    """角色注册表应跟踪角色的活跃章节范围。"""
    scenes = [
        {"id": "ch1-scene0", "chapter": 1, "text": "韩立出场。", "major_characters": ["韩立"], "raw_character_mentions": ["韩立", "韩立"]},
        {"id": "ch5-scene1", "chapter": 5, "text": "韩立再次出现。", "major_characters": ["韩立"], "raw_character_mentions": ["韩立", "韩立"]},
    ]

    registry = CharacterRegistryBuilder(seed_aliases={}).build(scenes)

    assert registry[0]["first_seen_chapter"] == 1
    assert registry[0]["last_seen_chapter"] == 5
    assert registry[0]["active_range"] == [1, 5]


def test_registry_tracks_co_occurring_characters():
    """角色注册表应跟踪共同出现的角色。"""
    scenes = [
        {
            "id": "ch1-scene0",
            "chapter": 1,
            "text": "韩立和张铁一起出现。",
            "major_characters": ["韩立", "张铁"],
            "raw_character_mentions": ["韩立", "韩立", "张铁", "张铁"],
        }
    ]

    registry = CharacterRegistryBuilder(seed_aliases={}).build(scenes)

    han_li = next((entry for entry in registry if entry["canonical_name"] == "韩立"), None)
    assert han_li is not None
    assert "张铁" in han_li["co_occurring_characters"]


def test_registry_preserves_evidence_scene_ids():
    """角色注册表应保留证据场景ID。"""
    scenes = [
        {
            "id": "ch1-scene0",
            "chapter": 1,
            "text": "韩立出场。",
            "major_characters": ["韩立"],
            "raw_character_mentions": ["韩立", "韩立"],
        },
        {
            "id": "ch2-scene1",
            "chapter": 2,
            "text": "韩立再次出现。",
            "major_characters": ["韩立"],
            "raw_character_mentions": ["韩立", "韩立"],
        },
    ]

    registry = CharacterRegistryBuilder(seed_aliases={}).build(scenes)

    assert "ch1-scene0" in registry[0]["evidence_scene_ids"]
    assert "ch2-scene1" in registry[0]["evidence_scene_ids"]


# =============================================================================
# Evidence-based filtering tests (US-003)
# =============================================================================


def test_registry_filters_by_frequency_evidence():
    """角色注册表应根据出现频率过滤候选。"""
    scenes = [
        {
            "id": "ch1-scene0",
            "chapter": 1,
            "text": "韩立韩立韩立出现多次。",
            "major_characters": ["韩立"],
            "raw_character_mentions": ["韩立", "韩立", "韩立"],
        },
        {
            "id": "ch1-scene1",
            "chapter": 1,
            "text": "龙套只出现一次。",
            "major_characters": ["龙套"],
            "raw_character_mentions": ["龙套"],
        },
    ]

    thresholds = FilterThresholds(min_frequency=2, min_chapter_span=1, min_scene_count=1)
    registry = CharacterRegistryBuilder(seed_aliases={}, thresholds=thresholds).build(scenes)

    # 韩立 passes (3 mentions), 龙套 filtered (1 mention)
    canonical_names = {entry["canonical_name"] for entry in registry}
    assert "韩立" in canonical_names
    assert "龙套" not in canonical_names


def test_registry_filters_by_chapter_span_evidence():
    """角色注册表应根据章节跨度过滤候选。"""
    scenes = [
        {
            "id": "ch1-scene0",
            "chapter": 1,
            "text": "韩立出现。",
            "major_characters": ["韩立"],
            "raw_character_mentions": ["韩立", "韩立"],
        },
        {
            "id": "ch2-scene0",
            "chapter": 2,
            "text": "韩立再次出现。",
            "major_characters": ["韩立"],
            "raw_character_mentions": ["韩立", "韩立"],
        },
        {
            "id": "ch1-scene1",
            "chapter": 1,
            "text": "路人只在一章出现两次。",
            "major_characters": ["路人"],
            "raw_character_mentions": ["路人", "路人"],
        },
    ]

    thresholds = FilterThresholds(min_frequency=2, min_chapter_span=2, min_scene_count=1)
    registry = CharacterRegistryBuilder(seed_aliases={}, thresholds=thresholds).build(scenes)

    # 韩立 passes (2 chapters), 路人 filtered (1 chapter)
    canonical_names = {entry["canonical_name"] for entry in registry}
    assert "韩立" in canonical_names
    assert "路人" not in canonical_names


def test_registry_filters_by_scene_evidence():
    """角色注册表应根据场景数量过滤候选。"""
    scenes = [
        {
            "id": "ch1-scene0",
            "chapter": 1,
            "text": "韩立出现。",
            "major_characters": ["韩立"],
            "raw_character_mentions": ["韩立", "韩立"],
        },
        {
            "id": "ch1-scene1",
            "chapter": 1,
            "text": "韩立再次出现。",
            "major_characters": ["韩立"],
            "raw_character_mentions": ["韩立", "韩立"],
        },
        {
            "id": "ch1-scene2",
            "chapter": 1,
            "text": "路人在单场景出现两次。",
            "major_characters": ["路人"],
            "raw_character_mentions": ["路人", "路人"],
        },
    ]

    thresholds = FilterThresholds(min_frequency=2, min_chapter_span=1, min_scene_count=2)
    registry = CharacterRegistryBuilder(seed_aliases={}, thresholds=thresholds).build(scenes)

    # 韩立 passes (2 scenes), 路人 filtered (1 scene)
    canonical_names = {entry["canonical_name"] for entry in registry}
    assert "韩立" in canonical_names
    assert "路人" not in canonical_names


def test_registry_preserves_seed_characters_regardless_of_evidence():
    """种子角色应无视证据阈值保留。"""
    scenes = [
        {
            "id": "ch1-scene0",
            "chapter": 1,
            "text": "韩立只出现一次。",
            "major_characters": ["韩立"],
            "raw_character_mentions": ["韩立"],
        },
    ]

    # High thresholds would normally filter out single-mention characters
    thresholds = FilterThresholds(min_frequency=5, min_chapter_span=3, min_scene_count=3)
    registry = CharacterRegistryBuilder(
        seed_aliases={"韩立": ["二愣子"]},
        thresholds=thresholds
    ).build(scenes)

    # 韩立 is preserved because it's a seed character
    assert len(registry) == 1
    assert registry[0]["canonical_name"] == "韩立"


def test_registry_tracks_evidence_counts():
    """角色注册表应跟踪证据计数。"""
    scenes = [
        {
            "id": "ch1-scene0",
            "chapter": 1,
            "text": "韩立韩立韩立出现。",
            "major_characters": ["韩立"],
            "raw_character_mentions": ["韩立", "韩立", "韩立"],
        },
        {
            "id": "ch2-scene0",
            "chapter": 2,
            "text": "韩立再次出现。",
            "major_characters": ["韩立"],
            "raw_character_mentions": ["韩立", "韩立"],
        },
    ]

    registry = CharacterRegistryBuilder(seed_aliases={}).build(scenes)

    assert len(registry) == 1
    entry = registry[0]
    assert entry["frequency_evidence"] == 5  # 3 + 2 mentions
    assert entry["chapter_span_evidence"] == 2  # chapters 1 and 2
    assert entry["scene_evidence"] == 2  # two scenes


def test_registry_confidence_based_on_evidence():
    """角色注册表应根据证据计算置信度。"""
    scenes = [
        {
            "id": "ch1-scene0",
            "chapter": 1,
            "text": "韩立韩立韩立出现。",
            "major_characters": ["韩立"],
            "raw_character_mentions": ["韩立", "韩立", "韩立"],
        },
        {
            "id": "ch2-scene0",
            "chapter": 2,
            "text": "韩立再次出现。",
            "major_characters": ["韩立"],
            "raw_character_mentions": ["韩立"],
        },
    ]

    registry = CharacterRegistryBuilder(seed_aliases={}).build(scenes)

    # Character with more evidence should have higher confidence
    assert registry[0]["confidence"] > 0.5


def test_registry_deterministic_ordering():
    """角色注册表应产生确定性排序结果。"""
    scenes = [
        {
            "id": "ch1-scene0",
            "chapter": 1,
            "text": "张铁韩立出现。",
            "major_characters": ["张铁", "韩立"],
            "raw_character_mentions": ["张铁", "韩立", "张铁", "韩立"],
        },
    ]

    # Run multiple times to ensure deterministic output
    results = []
    for _ in range(3):
        registry = CharacterRegistryBuilder(seed_aliases={}).build(scenes)
        results.append([entry["canonical_name"] for entry in registry])

    # All results should be identical
    assert results[0] == results[1] == results[2]


def test_registry_full_filtering_pipeline():
    """角色注册表应完整执行候选抽取和过滤链路。"""
    scenes = [
        # Main character: high frequency, multiple chapters, multiple scenes
        {
            "id": "ch1-scene0",
            "chapter": 1,
            "text": "韩立韩立韩立出现。",
            "major_characters": ["韩立"],
            "raw_character_mentions": ["韩立", "韩立", "韩立"],
        },
        {
            "id": "ch2-scene0",
            "chapter": 2,
            "text": "韩立韩立出现。",
            "major_characters": ["韩立"],
            "raw_character_mentions": ["韩立", "韩立"],
        },
        {
            "id": "ch3-scene0",
            "chapter": 3,
            "text": "韩立韩立出现。",
            "major_characters": ["韩立"],
            "raw_character_mentions": ["韩立", "韩立"],
        },
        # Secondary character: medium frequency, multiple scenes, single chapter
        {
            "id": "ch1-scene1",
            "chapter": 1,
            "text": "张铁张铁出现。",
            "major_characters": ["张铁"],
            "raw_character_mentions": ["张铁", "张铁"],
        },
        {
            "id": "ch1-scene2",
            "chapter": 1,
            "text": "张铁张铁出现。",
            "major_characters": ["张铁"],
            "raw_character_mentions": ["张铁", "张铁"],
        },
        # Minor character: low frequency
        {
            "id": "ch1-scene3",
            "chapter": 1,
            "text": "龙套出现。",
            "major_characters": ["龙套"],
            "raw_character_mentions": ["龙套"],
        },
    ]

    thresholds = FilterThresholds(min_frequency=2, min_chapter_span=1, min_scene_count=2)
    registry = CharacterRegistryBuilder(seed_aliases={}, thresholds=thresholds).build(scenes)

    # 韩立: 7 mentions, 3 chapters, 3 scenes → passes
    # 张铁: 4 mentions, 1 chapter, 2 scenes → passes
    # 龙套: 1 mention → filtered
    canonical_names = {entry["canonical_name"] for entry in registry}
    assert "韩立" in canonical_names
    assert "张铁" in canonical_names
    assert "龙套" not in canonical_names
