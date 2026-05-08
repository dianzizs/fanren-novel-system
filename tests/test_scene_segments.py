"""Tests for scene segmentation."""
import json

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


# =============================================================================
# POS tagging-based candidate extraction tests (US-003)
# =============================================================================


def test_pos_tagging_extracts_person_names():
    """分词词性标注应识别人物名称。"""
    chapter = {
        "chapter": 1,
        "title": "测试",
        "paragraphs": [
            "韩立皱眉道：此事有些蹊跷。张铁走了过来。",
        ],
    }

    scenes = SceneSegmentBuilder().build([chapter])
    mentions = scenes[0]["raw_character_mentions"]

    assert "韩立" in mentions
    assert "张铁" in mentions


def test_pos_tagging_catches_names_regex_misses():
    """词性标注应能捕获正则遗漏的人名（非常见姓氏）。"""
    chapter = {
        "chapter": 1,
        "title": "测试",
        "paragraphs": [
            "令狐冲说道：今日天气不错。任盈盈点了点头。",
        ],
    }

    scenes = SceneSegmentBuilder().build([chapter])
    mentions = scenes[0]["raw_character_mentions"]

    # jieba POS tagging should identify these as person names (nr)
    # even though 令狐/任 might not be in COMMON_SURNAMES
    assert any("令狐冲" in m or "令狐" in m for m in mentions) or \
           any("任盈盈" in m or "任盈" in m for m in mentions)


def test_pos_tagging_excludes_non_person_words():
    """词性标注应排除非人名词。"""
    chapter = {
        "chapter": 1,
        "title": "测试",
        "paragraphs": [
            "时间过得很快。方法不对。",
        ],
    }

    scenes = SceneSegmentBuilder().build([chapter])
    mentions = scenes[0]["raw_character_mentions"]

    # These should NOT appear as character mentions
    assert "时间" not in mentions
    assert "方法" not in mentions


def test_candidate_extraction_results_are_serializable():
    """候选抽取结果应可序列化为 JSON。"""
    chapter = {
        "chapter": 1,
        "title": "测试",
        "paragraphs": [
            "韩立和张铁来到七玄门。墨大夫皱眉道：你们来了。",
        ],
    }

    scenes = SceneSegmentBuilder().build([chapter])

    # Should be JSON serializable
    json_str = json.dumps(scenes, ensure_ascii=False)
    assert json_str
    assert "韩立" in json_str

    # Round-trip should preserve data
    restored = json.loads(json_str)
    assert len(restored) == len(scenes)
    assert restored[0]["raw_character_mentions"] == scenes[0]["raw_character_mentions"]


def test_candidate_extraction_is_deterministic():
    """候选抽取应产生确定性结果。"""
    chapter = {
        "chapter": 1,
        "title": "测试",
        "paragraphs": [
            "韩立和张铁来到七玄门。墨大夫皱眉道：你们来了。",
        ],
    }

    results = []
    for _ in range(3):
        scenes = SceneSegmentBuilder().build([chapter])
        results.append(scenes[0]["raw_character_mentions"])

    assert results[0] == results[1] == results[2]
