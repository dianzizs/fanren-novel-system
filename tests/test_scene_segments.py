"""Tests for scene segmentation."""
from novel_system.artifacts.scene_segments import SceneSegmentBuilder


def test_scene_builder_splits_on_location_shift():
    """场景应根据地点转换进行分割。"""
    chapter = {
        "chapter": 12,
        "title": "试炼前夜",
        "paragraphs": [
            "韩立在屋内盘膝打坐，默默运转长春功。",
            "片刻后他推门而出，来到青石广场，看见张铁已经等在那里。",
        ],
    }

    scenes = SceneSegmentBuilder().build([chapter])

    assert len(scenes) == 2
    assert scenes[0]["id"] == "ch12-scene0"
    assert scenes[1]["id"] == "ch12-scene1"
    assert scenes[0]["paragraph_start"] == 0
    assert scenes[1]["paragraph_start"] == 1


def test_scene_builder_carries_character_mentions():
    """场景应包含主要角色信息。"""
    chapter = {
        "chapter": 1,
        "title": "山边小村",
        "paragraphs": [
            "韩立被村里人叫作二愣子。",
            "三叔笑眯眯地望着韩立，和韩父韩母说起七玄门。",
        ],
    }

    scenes = SceneSegmentBuilder().build([chapter])

    assert scenes[0]["major_characters"]
    assert "韩立" in scenes[0]["raw_character_mentions"]


def test_scene_builder_preserves_text_and_metadata():
    """场景应保留文本和元数据。"""
    chapter = {
        "chapter": 5,
        "title": "青牛镇",
        "paragraphs": [
            "韩立来到青牛镇。",
            "他看见张铁和三叔。",
        ],
    }

    scenes = SceneSegmentBuilder().build([chapter])

    assert len(scenes) == 1
    assert scenes[0]["chapter"] == 5
    assert scenes[0]["title"] == "青牛镇"
    assert "韩立来到青牛镇" in scenes[0]["text"]
    assert scenes[0]["paragraph_start"] == 0
    assert scenes[0]["paragraph_end"] == 1
