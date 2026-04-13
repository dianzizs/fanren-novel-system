"""Tests for character registry building."""
from novel_system.artifacts.character_registry import CharacterRegistryBuilder


def test_registry_merges_alias_into_canonical_name():
    """角色注册表应将别名合并到规范名称。"""
    scenes = [
        {
            "id": "ch1-scene0",
            "chapter": 1,
            "text": "韩立被村里人叫作二愣子。",
            "major_characters": ["韩立", "二愣子"],
            "raw_character_mentions": ["韩立", "二愣子"],
        }
    ]

    registry = CharacterRegistryBuilder(seed_aliases={"韩立": ["二愣子"]}).build(scenes)

    assert len(registry) == 1
    assert registry[0]["canonical_name"] == "韩立"
    assert "二愣子" in registry[0]["aliases"]


def test_registry_tracks_active_range():
    """角色注册表应跟踪角色的活跃章节范围。"""
    scenes = [
        {"id": "ch1-scene0", "chapter": 1, "text": "韩立出场。", "major_characters": ["韩立"], "raw_character_mentions": ["韩立"]},
        {"id": "ch5-scene1", "chapter": 5, "text": "韩立再次出现。", "major_characters": ["韩立"], "raw_character_mentions": ["韩立"]},
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
            "raw_character_mentions": ["韩立", "张铁"],
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
            "raw_character_mentions": ["韩立"],
        },
        {
            "id": "ch2-scene1",
            "chapter": 2,
            "text": "韩立再次出现。",
            "major_characters": ["韩立"],
            "raw_character_mentions": ["韩立"],
        },
    ]

    registry = CharacterRegistryBuilder(seed_aliases={}).build(scenes)

    assert "ch1-scene0" in registry[0]["evidence_scene_ids"]
    assert "ch2-scene1" in registry[0]["evidence_scene_ids"]
