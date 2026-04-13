"""Scene segmentation for novel text.

A scene is a coherent unit of narrative action, typically bounded by:
- Location changes (来到, 走到, 出了, 进了, 回到)
- Time jumps
- Perspective shifts

Scene segments serve as the primary unit for retrieval and event extraction.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any


LOCATION_SHIFT_RE = re.compile(r"(来到|走到|出了|进了|回到|在.+?广场|在.+?屋内)")

# Common Chinese surnames for person name detection
COMMON_SURNAMES = (
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    "谢邹喻柏水窦章云苏潘葛范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费岑"
    "薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元顾孟平黄和穆萧尹"
    "姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵"
    "席季麻强贾路江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯管卢"
    "莫经房裘缪解应宗丁宣邓郁单杭洪包诸左石崔吉龚程嵇邢裴陆荣翁荀羊於"
    "惠甄家封芮储靳汲松井段富巫焦巴弓牧隗山谷车侯伊宁仇栾暴甘武符刘景"
    "詹束龙叶司"
)
PERSON_RE = re.compile(rf"([{COMMON_SURNAMES}][\u4e00-\u9fff]{{1,2}})")
TITLE_PERSON_RE = re.compile(
    r"([\u4e00-\u9fff]{1,4}(?:大夫|护法|堂主|门主|师兄|师姐|师父|长老|掌柜|胖子|师叔|师伯|叔))"
)

# Names to exclude from character detection
STOP_NAMES = {
    "自己", "时候", "这里", "那里", "他们", "我们", "你们", "本来", "终于",
    "虽然", "不过", "如果", "因为", "就是", "只是", "这个", "那个", "怎么",
    "什么", "不是", "没有", "可以", "已经", "只有", "一个", "一下", "突然",
    "立刻", "于是", "同时", "东西", "地方", "七玄门", "七绝堂", "神手谷",
    "彩霞山", "青牛镇",
}

# Bad endings for names
BAD_NAME_ENDINGS = set(
    "的了呢啊呀吗吧着将会是在与及又仍把被向到进出上下来去回过后中里外前后时处所带让"
    "心一一不这也就听有也和自见看没还脸对大才等并望皱想说道做给比往走更被叫早已正用"
    "觉知该当从只已又如为何但却虽再向能需可应最都"
)


class SceneSegmentBuilder:
    """Builds scene segments from parsed chapters.

    Scenes are split on location shifts and carry character mentions.
    Each scene gets a stable ID for cross-referencing.
    """

    def build(self, chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Build scene segments from chapters.

        Args:
            chapters: List of chapter dicts with 'chapter', 'title', 'paragraphs' keys.

        Returns:
            List of scene segment dicts with metadata.
        """
        scenes: list[dict[str, Any]] = []
        for chapter in chapters:
            current: list[str] = []
            start_index = 0
            scene_index = 0
            for paragraph_index, paragraph in enumerate(chapter.get("paragraphs", [])):
                if current and self._is_boundary(current[-1], paragraph):
                    scenes.append(
                        self._make_scene(chapter, scene_index, start_index, paragraph_index - 1, current)
                    )
                    scene_index += 1
                    current = []
                    start_index = paragraph_index
                current.append(paragraph)
            if current:
                scenes.append(
                    self._make_scene(chapter, scene_index, start_index, start_index + len(current) - 1, current)
                )
        return scenes

    def _is_boundary(self, previous: str, current: str) -> bool:
        """Detect if there's a scene boundary between paragraphs."""
        return bool(LOCATION_SHIFT_RE.search(current) and previous != current)

    def _make_scene(
        self,
        chapter: dict[str, Any],
        scene_index: int,
        start_index: int,
        end_index: int,
        paragraphs: list[str],
    ) -> dict[str, Any]:
        """Create a scene segment dict."""
        text = "\n".join(paragraphs)
        mentions = self._extract_person_names(text)
        ranked_mentions = [name for name, _ in Counter(mentions).most_common(6)]
        return {
            "id": f"ch{chapter['chapter']}-scene{scene_index}",
            "chapter": chapter["chapter"],
            "scene_index": scene_index,
            "title": chapter["title"],
            "text": text,
            "paragraph_start": start_index,
            "paragraph_end": end_index,
            "char_start": 0,
            "char_end": len(text),
            "scene_summary": text[:120],
            "major_characters": ranked_mentions[:3],
            "raw_character_mentions": ranked_mentions,
            "event_ids": [],
            "spoiler_level": "current",
            "prev_scene_id": None if scene_index == 0 else f"ch{chapter['chapter']}-scene{scene_index - 1}",
            "next_scene_id": None,
        }

    def _extract_person_names(self, text: str) -> list[str]:
        """Extract person names using surname patterns and title patterns."""
        names = []
        for regex in (PERSON_RE, TITLE_PERSON_RE):
            for item in regex.findall(text):
                candidate = item.strip()
                # Filter out invalid names
                if (
                    len(candidate) < 2
                    or candidate in STOP_NAMES
                    or candidate[-1] in BAD_NAME_ENDINGS
                ):
                    continue
                # Filter out organization names
                if candidate.endswith("门") or candidate.endswith("帮") or candidate.endswith("山") or candidate.endswith("谷"):
                    continue
                names.append(candidate)
        frequency = Counter(names)
        return [name for name, _ in frequency.most_common() if name not in STOP_NAMES]
