"""Tests for artifact target builders."""
from novel_system.artifacts.targets import build_chapter_chunks, build_character_cards, build_event_timeline


def test_chapter_chunks_inherit_scene_metadata():
    """章节切片应继承场景元数据。"""
    scenes = [
        {
            "id": "ch2-scene0",
            "chapter": 2,
            "scene_index": 0,
            "title": "青牛镇",
            "text": "韩立来到青牛镇，看见张铁和三叔。",
            "paragraph_start": 0,
            "paragraph_end": 0,
            "char_start": 0,
            "char_end": 18,
            "major_characters": ["韩立", "张铁"],
            "event_ids": ["event-ch2-scene0-0"],
            "spoiler_level": "current",
        }
    ]

    chunks = build_chapter_chunks(scenes, chunk_size=10, overlap=2)

    assert chunks[0]["scene_id"] == "ch2-scene0"
    assert chunks[0]["major_characters"] == ["韩立", "张铁"]
    assert chunks[0]["event_ids"] == ["event-ch2-scene0-0"]


def test_event_timeline_from_scenes():
    """事件时间线应从场景生成。"""
    scenes = [
        {
            "id": "ch1-scene0",
            "chapter": 1,
            "scene_index": 0,
            "title": "山边小村",
            "text": "韩立被村里人叫作二愣子。",
            "scene_summary": "韩立被村里人叫作二愣子。",
            "major_characters": ["韩立"],
        }
    ]

    events = build_event_timeline(scenes)

    assert len(events) == 1
    assert events[0]["chapter"] == 1
    assert events[0]["scene_id"] == "ch1-scene0"
    assert "韩立" in events[0]["participants"]


def test_character_cards_are_registry_backed():
    """人物卡应基于角色注册表生成。"""
    registry = [
        {
            "character_id": "char-韩立",
            "canonical_name": "韩立",
            "aliases": ["二愣子"],
            "titles": [],
            "active_range": [1, 5],
            "evidence_scene_ids": ["ch1-scene0"],
        }
    ]
    scenes = [
        {
            "id": "ch1-scene0",
            "chapter": 1,
            "text": "韩立被叫作二愣子。",
            "major_characters": ["韩立"],
            "event_ids": ["event-ch1-scene0-0"],
        }
    ]
    events = [
        {
            "event_id": "event-ch1-scene0-0",
            "chapter": 1,
            "scene_id": "ch1-scene0",
            "participants": ["韩立"],
            "summary": "韩立被介绍",
        }
    ]

    cards = build_character_cards(registry, scenes, events)

    assert cards[0]["character_id"] == "char-韩立"
    assert cards[0]["canonical_name"] == "韩立"
    assert cards[0]["related_event_ids"] == ["event-ch1-scene0-0"]


def test_chapter_chunks_with_multiple_chunks_per_scene():
    """长场景应生成多个切片。"""
    scenes = [
        {
            "id": "ch1-scene0",
            "chapter": 1,
            "scene_index": 0,
            "title": "测试章节",
            "text": "这是一段很长的文本，" * 50,  # 约450字符
            "paragraph_start": 0,
            "paragraph_end": 0,
            "char_start": 0,
            "char_end": 450,
            "major_characters": [],
            "event_ids": [],
            "spoiler_level": "current",
        }
    ]

    chunks = build_chapter_chunks(scenes, chunk_size=100, overlap=20)

    assert len(chunks) >= 2
    # 每个切片应有正确的索引
    for i, chunk in enumerate(chunks):
        assert chunk["chunk_index_in_scene"] == i
