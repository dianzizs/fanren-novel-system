from __future__ import annotations

from .service_shared import *


class GraphService:
    def get_canon(self, book_id: str, scope: Scope | None = None) -> dict[str, Any]:
        self.ensure_indexed(book_id)
        book_index = self.repo.load(book_id)
        scope = scope or Scope()
        items = [
            doc["text"]
            for doc in book_index.corpora.get("canon_memory", [])
            if scope_filter(int(doc.get("chapter", 0)), scope.chapters)
        ][:20]
        items.extend(self._load_user_canon(book_id))
        return {"book_id": book_id, "items": items}

    def update_canon(self, book_id: str, payload: CanonUpdateRequest) -> dict[str, Any]:
        current = self._load_user_canon(book_id)
        merged = list(dict.fromkeys(current + payload.items))
        path = self._user_canon_path(book_id)
        path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"book_id": book_id, "items": merged}

    def get_timeline(self, book_id: str, scope: Scope | None = None) -> list[TimelineEvent]:
        self.ensure_indexed(book_id)
        book_index = self.repo.load(book_id)
        scope = scope or Scope()
        events = []
        for doc in book_index.corpora.get("event_timeline", []):
            chapter = int(doc.get("chapter", 0))
            if not scope_filter(chapter, scope.chapters):
                continue
            events.append(
                TimelineEvent(
                    chapter=chapter,
                    title=doc.get("title", ""),
                    description=doc.get("description", doc.get("text", "")),
                    participants=doc.get("participants", []),
                )
            )
        return events

    def get_interactive_graph(
        self,
        book_id: str,
        scope: Scope | None = None,
        *,
        center: str | None = None,
        limit: int = 18,
    ) -> dict[str, Any]:
        self.ensure_indexed(book_id)
        book_index = self.repo.load(book_id)
        scope = scope or Scope()
        limit = max(8, min(limit, 28))

        character_docs = [
            (index, doc)
            for index, doc in enumerate(book_index.corpora.get("character_card", []))
            if scope_filter(int(doc.get("chapter", 0)), scope.chapters)
        ]
        event_docs = [
            (index, doc)
            for index, doc in enumerate(book_index.corpora.get("event_timeline", []))
            if scope_filter(int(doc.get("chapter", 0)), scope.chapters)
        ]
        if not character_docs or not event_docs:
            return {
                "nodes": [],
                "edges": [],
                "available_characters": [],
                "center": None,
                "scope": scope.model_dump(),
                "stats": {"character_count": 0, "event_count": 0, "edge_count": 0},
            }

        raw_scores = self._build_graph_name_scores(character_docs, event_docs)
        known_names = self._seed_graph_known_names(raw_scores)

        character_buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        character_scores: dict[str, float] = defaultdict(float)
        for index, doc in character_docs:
            canonical = self._canonicalize_graph_name(str(doc.get("name", "")), known_names)
            if not canonical:
                continue
            character_buckets[canonical].append({"index": index, "doc": doc})
            character_scores[canonical] += 1.2 + min(len(doc.get("chapters", [])) / 6, 4)

        normalized_events: list[dict[str, Any]] = []
        event_character_support: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"chapters": set(), "snippets": [], "count": 0}
        )
        for index, doc in event_docs:
            participants = []
            for name in doc.get("participants", []):
                canonical = self._canonicalize_graph_name(str(name), known_names)
                if canonical and canonical not in participants:
                    participants.append(canonical)
                    character_scores[canonical] += 0.8
            event = {
                "index": index,
                "id": str(doc.get("id", f"event-{doc.get('chapter', 0)}")),
                "chapter": int(doc.get("chapter", 0)),
                "title": str(doc.get("title", "")),
                "description": str(doc.get("description", doc.get("text", ""))),
                "participants": participants,
            }
            normalized_events.append(event)
            for participant in participants:
                support = event_character_support[participant]
                support["chapters"].add(event["chapter"])
                support["count"] += 1
                if len(support["snippets"]) < 3 and event["description"]:
                    support["snippets"].append(event["description"])

        center_name = self._canonicalize_graph_name(center or "", known_names) if center else None
        center_affinity_scores: dict[str, float] = defaultdict(float)
        if center_name:
            for event in normalized_events:
                if center_name not in event["participants"]:
                    continue
                for participant in event["participants"]:
                    if participant != center_name:
                        center_affinity_scores[participant] += 1.4

        available_characters = [
            name
            for name, _ in sorted(
                character_scores.items(),
                key=lambda item: (
                    item[1]
                    + center_affinity_scores.get(item[0], 0.0) * 2.2
                    + (1.2 if item[0] in GRAPH_CANON_SEEDS else 0.0),
                    item[0],
                ),
                reverse=True,
            )
            if self._looks_like_graph_name(name)
        ][:60]
        if center_name and center_name not in available_characters:
            available_characters.insert(0, center_name)

        character_query_scores = self._graph_character_query_scores(book_index, character_docs, known_names, center_name)
        ranked_characters = sorted(
            character_scores.items(),
            key=lambda item: (
                item[1]
                + character_query_scores.get(item[0], 0.0) * 6
                + center_affinity_scores.get(item[0], 0.0) * 3.5
                + (1.6 if item[0] in GRAPH_CANON_SEEDS else 0.0)
                + (5 if item[0] == center_name else 0)
            ),
            reverse=True,
        )
        character_limit = max(8, min(14, limit))
        selected_characters: list[str] = []
        if center_name:
            selected_characters.append(center_name)
        for name, _ in ranked_characters:
            if not character_buckets.get(name) and not event_character_support.get(name):
                continue
            if name not in selected_characters:
                selected_characters.append(name)
            if len(selected_characters) >= character_limit:
                break

        representative_docs = {
            name: self._select_representative_character_doc(character_buckets.get(name, []))
            for name in selected_characters
            if character_buckets.get(name)
        }
        character_profiles: dict[str, dict[str, Any]] = {}
        for name in selected_characters:
            representative = representative_docs.get(name)
            if representative:
                doc = representative["doc"]
                character_profiles[name] = {
                    "index": representative["index"],
                    "chapter": int(doc.get("chapter", 0)),
                    "summary": self._trim_quote(str(doc.get("text", "")), 180),
                    "chapters": doc.get("chapters", [])[:12],
                    "aliases": doc.get("aliases", []),
                }
                continue
            support = event_character_support.get(name)
            if support:
                character_profiles[name] = self._build_event_backed_character_doc(name, support)

        event_query_scores = self._graph_event_query_scores(book_index, event_docs, center_name)
        event_rankings: list[tuple[float, dict[str, Any]]] = []
        for event in normalized_events:
            shared_characters = [name for name in event["participants"] if name in selected_characters]
            if not shared_characters:
                continue
            event["shared_characters"] = shared_characters
            score = len(shared_characters) * 2 + event_query_scores.get(event["id"], 0.0) * 4
            if center_name and center_name in shared_characters:
                score += 1.5
            event_rankings.append((score, event))
        event_rankings.sort(key=lambda item: (item[0], -item[1]["chapter"]), reverse=True)
        event_limit = max(6, min(limit, 10))
        selected_events = [item[1] for item in event_rankings[:event_limit]]
        selected_events.sort(key=lambda item: item["chapter"])

        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        for name in selected_characters:
            profile = character_profiles.get(name)
            if not profile:
                continue
            nodes.append(
                {
                    "id": f"char::{name}",
                    "label": name,
                    "type": "character",
                    "size": round(13 + min(character_scores.get(name, 0), 8), 2),
                    "chapter": profile["chapter"],
                    "summary": profile["summary"],
                    "chapters": profile["chapters"],
                    "aliases": profile["aliases"],
                    "is_center": name == center_name,
                }
            )

        for event in selected_events:
            nodes.append(
                {
                    "id": f"event::{event['id']}",
                    "label": f"Ch.{event['chapter']} {event['title']}",
                    "type": "event",
                    "size": round(10 + min(len(event['shared_characters']) * 1.5, 7), 2),
                    "chapter": event["chapter"],
                    "summary": self._trim_quote(event["description"], 200),
                    "participants": event["shared_characters"],
                    "is_center": False,
                }
            )

        character_pair_counts: dict[tuple[str, str], int] = defaultdict(int)
        for event in selected_events:
            shared_characters = event["shared_characters"]
            for character in shared_characters:
                edges.append(
                    {
                        "source": f"char::{character}",
                        "target": f"event::{event['id']}",
                        "weight": 1.0,
                        "type": "participates_in",
                        "label": f"{character} appears in {event['title']}",
                    }
                )
            for index, left in enumerate(shared_characters):
                for right in shared_characters[index + 1 :]:
                    character_pair_counts[tuple(sorted((left, right)))] += 1

        for index in range(len(selected_events) - 1):
            left = selected_events[index]
            right = selected_events[index + 1]
            edges.append(
                {
                    "source": f"event::{left['id']}",
                    "target": f"event::{right['id']}",
                    "weight": 0.5,
                    "type": "timeline_next",
                    "label": "timeline",
                }
            )

        for index, left_name in enumerate(selected_characters):
            left_profile = character_profiles.get(left_name)
            if not left_profile:
                continue
            for right_name in selected_characters[index + 1 :]:
                right_profile = character_profiles.get(right_name)
                if not right_profile:
                    continue
                shared_events = character_pair_counts.get(tuple(sorted((left_name, right_name))), 0)
                similarity = 0.0
                if left_profile.get("index") is not None and right_profile.get("index") is not None:
                    similarity = self._graph_character_similarity(
                        book_index,
                        left_profile["index"],
                        right_profile["index"],
                    )
                if shared_events <= 0 and similarity < 0.12:
                    continue
                edges.append(
                    {
                        "source": f"char::{left_name}",
                        "target": f"char::{right_name}",
                        "weight": round(shared_events * 1.4 + similarity * 6, 3),
                        "type": "character_relation",
                        "label": f"shared_events={shared_events}, vector_similarity={similarity:.2f}",
                    }
                )

        return {
            "nodes": nodes,
            "edges": edges,
            "available_characters": available_characters,
            "center": center_name,
            "scope": scope.model_dump(),
            "stats": {
                "character_count": sum(1 for node in nodes if node["type"] == "character"),
                "event_count": len(selected_events),
                "edge_count": len(edges),
            },
        }

    def _chapter_summary(self, book_index: Any, chapter: int) -> str:
        for item in book_index.corpora.get("chapter_summaries", []):
            if item.get("chapter") == chapter:
                return item.get("text", "")
        return ""

    def _user_canon_path(self, book_id: str) -> Path:
        self.config.runtime_dir.mkdir(parents=True, exist_ok=True)
        return self.config.runtime_dir / f"{book_id}_user_canon.json"

    def _load_user_canon(self, book_id: str) -> list[str]:
        path = self._user_canon_path(book_id)
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def _build_graph_name_scores(
        self,
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

    def _seed_graph_known_names(self, raw_scores: dict[str, float]) -> set[str]:
        known = set(GRAPH_CANON_SEEDS)
        known.update(ALIAS_MAP)
        known.update(GRAPH_ALIAS_LOOKUP.values())
        short_names: set[str] = set()
        for name, score in raw_scores.items():
            if score < 2 and name not in GRAPH_CANON_SEEDS:
                continue
            if any(name.endswith(suffix) for suffix in GRAPH_TITLE_SUFFIXES):
                known.add(name)
                continue
            if len(name) == 2 and self._looks_like_graph_name(name):
                short_names.add(name)
                known.add(name)
        for name, score in raw_scores.items():
            if (score < 2 and name not in GRAPH_CANON_SEEDS) or name in known:
                continue
            if not self._looks_like_graph_name(name):
                continue
            if (
                name not in GRAPH_CANON_SEEDS
                and len(name) in {3, 4}
                and any(name.startswith(base) or name.endswith(base) for base in short_names)
            ):
                continue
            known.add(name)
        return known

    def _canonicalize_graph_name(self, raw_name: str, known_names: set[str]) -> str | None:
        name = raw_name.strip()
        if not name:
            return None
        if name in GRAPH_ALIAS_LOOKUP:
            return GRAPH_ALIAS_LOOKUP[name]
        if name in GRAPH_CANON_SEEDS or name in ALIAS_MAP:
            return name
        if name in known_names and self._looks_like_graph_name(name):
            return name

        sorted_known = sorted(known_names, key=len, reverse=True)
        for base in sorted_known:
            if not base:
                continue
            if name == base:
                return base
            if name.startswith(base) and (
                len(name) == len(base) + 1 or self._is_generic_graph_fragment(name[len(base) :])
            ):
                return base
            if name.endswith(base) and (
                len(name) == len(base) + 1 or self._is_generic_graph_fragment(name[: -len(base)])
            ):
                return base

        if self._looks_like_graph_name(name):
            return name
        return None

    def _looks_like_graph_name(self, name: str) -> bool:
        if not name or name in GRAPH_GENERIC_NAMES:
            return False
        if any(fragment in name for fragment in GRAPH_GENERIC_SUBSTRINGS):
            return False
        if name in GRAPH_CANON_SEEDS or name in ALIAS_MAP or name in GRAPH_ALIAS_LOOKUP:
            return True
        if any(name.endswith(suffix) for suffix in GRAPH_TITLE_SUFFIXES):
            return True
        if len(name) < 2 or len(name) > 4:
            return False
        if self._is_generic_graph_fragment(name):
            return False
        if name[0] in GRAPH_BAD_START_CHARS:
            return False
        if name[0] not in COMMON_SURNAMES:
            return False
        if len(name) >= 3 and any(char in GRAPH_GENERIC_FRAGMENT_CHARS for char in name[1:-1]):
            return False
        if len(name) == 2 and name[1] in GRAPH_GENERIC_FRAGMENT_CHARS.union({"子", "氏", "们", "个"}):
            return False
        if name[-1] in GRAPH_BAD_END_CHARS:
            return False
        if name[-1] in GRAPH_GENERIC_FRAGMENT_CHARS:
            return False
        return True

    def _is_generic_graph_fragment(self, fragment: str) -> bool:
        if not fragment:
            return True
        return all(char in GRAPH_GENERIC_FRAGMENT_CHARS for char in fragment)

    def _select_representative_character_doc(self, bucket: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not bucket:
            return None
        return max(
            bucket,
            key=lambda item: (
                len(item["doc"].get("chapters", [])),
                len(item["doc"].get("text", "")),
                -int(item["doc"].get("chapter", 0)),
            ),
        )

    def _build_event_backed_character_doc(self, name: str, support: dict[str, Any]) -> dict[str, Any]:
        chapters = sorted(int(chapter) for chapter in support.get("chapters", set()))
        snippets = [
            self._trim_quote(str(text), 72)
            for text in support.get("snippets", [])
            if text
        ]
        summary = f"姓名：{name}；当前范围内主要通过事件共现出现。"
        if snippets:
            summary += f" 相关线索：{'；'.join(snippets[:2])}"
        return {
            "index": None,
            "chapter": chapters[0] if chapters else 0,
            "summary": self._trim_quote(summary, 180),
            "chapters": chapters[:12],
            "aliases": ALIAS_MAP.get(name, []),
        }

    def _graph_character_query_scores(
        self,
        book_index: Any,
        character_docs: list[tuple[int, dict[str, Any]]],
        known_names: set[str],
        center_name: str | None,
    ) -> dict[str, float]:
        if not center_name:
            return {}
        vectorizer = book_index.vectorizers.get("character_card")
        matrix = book_index.matrices.get("character_card")
        if vectorizer is None or matrix is None:
            return {}
        query_vec = vectorizer.transform([center_name])
        raw_scores = (matrix @ query_vec.T).toarray().ravel()
        scores: dict[str, float] = defaultdict(float)
        for index, doc in character_docs:
            canonical = self._canonicalize_graph_name(str(doc.get("name", "")), known_names)
            if not canonical:
                continue
            scores[canonical] = max(scores[canonical], float(raw_scores[index]))
        return scores

    def _graph_event_query_scores(
        self,
        book_index: Any,
        event_docs: list[tuple[int, dict[str, Any]]],
        center_name: str | None,
    ) -> dict[str, float]:
        if not center_name:
            return {}
        vectorizer = book_index.vectorizers.get("event_timeline")
        matrix = book_index.matrices.get("event_timeline")
        if vectorizer is None or matrix is None:
            return {}
        query_vec = vectorizer.transform([center_name])
        raw_scores = (matrix @ query_vec.T).toarray().ravel()
        return {
            str(doc.get("id", f"event-{doc.get('chapter', 0)}")): float(raw_scores[index])
            for index, doc in event_docs
        }

    def _graph_character_similarity(
        self,
        book_index: Any,
        left_index: int,
        right_index: int,
    ) -> float:
        matrix = book_index.matrices.get("character_card")
        if matrix is None:
            return 0.0
        return float(matrix[left_index].multiply(matrix[right_index]).sum())

    def _inverse_score(self, value: float | None) -> float | None:
        if value is None:
            return None
        return round(1 - float(value), 4)

