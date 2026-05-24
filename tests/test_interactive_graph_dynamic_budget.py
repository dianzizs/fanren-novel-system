from novel_system.graph_service import GraphService


def test_auto_budget_expands_when_many_candidates():
    service = GraphService()
    budget = service._compute_graph_budget(
        density="auto",
        requested_limit=20,
        candidate_character_count=80,
        candidate_event_count=45,
        scope_chapter_count=14,
        has_center=False,
    )

    assert budget["density"] == "auto"
    assert budget["character_limit"] > 14
    assert budget["event_limit"] > 10
    assert budget["character_limit"] <= 28
    assert budget["event_limit"] <= 18


def test_compact_budget_preserves_current_small_graph_behavior():
    service = GraphService()
    budget = service._compute_graph_budget(
        density="compact",
        requested_limit=20,
        candidate_character_count=80,
        candidate_event_count=45,
        scope_chapter_count=14,
        has_center=False,
    )

    assert 8 <= budget["character_limit"] <= 14
    assert 6 <= budget["event_limit"] <= 10


def test_invalid_density_falls_back_to_auto():
    service = GraphService()
    budget = service._compute_graph_budget(
        density="surprise",
        requested_limit=20,
        candidate_character_count=40,
        candidate_event_count=20,
        scope_chapter_count=14,
        has_center=True,
    )

    assert budget["density"] == "auto"


def test_expanded_budget_gives_largest_range():
    service = GraphService()
    budget = service._compute_graph_budget(
        density="expanded",
        requested_limit=20,
        candidate_character_count=80,
        candidate_event_count=45,
        scope_chapter_count=14,
        has_center=False,
    )

    assert budget["density"] == "expanded"
    assert budget["character_limit"] >= 20
    assert budget["event_limit"] >= 12
    assert budget["character_limit"] <= 42
    assert budget["event_limit"] <= 28


def test_small_candidate_count_returns_all():
    service = GraphService()
    budget = service._compute_graph_budget(
        density="auto",
        requested_limit=20,
        candidate_character_count=5,
        candidate_event_count=3,
        scope_chapter_count=14,
        has_center=False,
    )

    assert budget["character_limit"] <= 5
    assert budget["event_limit"] <= 3


def test_center_preserves_minimum_one_slot():
    service = GraphService()
    budget = service._compute_graph_budget(
        density="auto",
        requested_limit=20,
        candidate_character_count=0,
        candidate_event_count=0,
        scope_chapter_count=1,
        has_center=True,
    )

    assert budget["character_limit"] >= 1


def test_graph_stats_include_dynamic_budget_metadata():
    """Test that get_interactive_graph returns budget metadata in stats."""
    from unittest.mock import patch, MagicMock

    service = GraphService()

    # Create a mock book_index with minimal required structure
    mock_book_index = MagicMock()
    mock_book_index.corpora = {
        "character_card": [
            {"name": "韩立", "chapter": 1, "chapters": [1, 2, 3], "text": "主角"},
            {"name": "南宫婉", "chapter": 2, "chapters": [2, 3], "text": "女主"},
        ],
        "event_timeline": [
            {"id": "e1", "chapter": 1, "title": "事件1", "description": "desc1", "participants": ["韩立"]},
            {"id": "e2", "chapter": 2, "title": "事件2", "description": "desc2", "participants": ["韩立", "南宫婉"]},
        ],
        "character_registry": [],
    }
    mock_book_index.vectorizers = {}
    mock_book_index.matrices = {}

    with patch.object(service, "ensure_indexed"), \
         patch.object(service.repo, "load", return_value=mock_book_index):
        from novel_system.models import Scope
        result = service.get_interactive_graph("test-book", Scope(chapters=[1, 2]), density="auto")

    stats = result["stats"]
    assert "density" in stats
    assert "character_limit" in stats
    assert "event_limit" in stats
    assert "candidate_character_count" in stats
    assert "candidate_event_count" in stats
    assert stats["density"] == "auto"
    assert stats["candidate_character_count"] >= stats["character_count"]
    assert stats["candidate_event_count"] >= stats["event_count"]


def test_candidate_tier_filters_unsupported_fragments():
    """Test that Tier 99 (unsupported) candidates are not selected."""
    service = GraphService()

    # Tier 1: seed name
    assert service._graph_candidate_tier(
        "韩立",
        seed_names={"韩立"},
        character_buckets={"韩立": [{"doc": {}}]},
        event_character_support={"韩立": {"count": 1}},
    ) == 1

    # Tier 2: has character card and event support
    assert service._graph_candidate_tier(
        "南宫婉",
        seed_names=set(),
        character_buckets={"南宫婉": [{"doc": {}}]},
        event_character_support={"南宫婉": {"count": 1}},
    ) == 2

    # Tier 3: has character card but no event support, passes name check
    # (depends on _looks_like_graph_name, which we can't easily mock here)
    # So just test Tier 99

    # Tier 99: no support at all
    assert service._graph_candidate_tier(
        "碎片",
        seed_names=set(),
        character_buckets={},
        event_character_support={},
    ) == 99


def test_relationship_graph_provides_edge_evidence():
    """Test that relationship_graph evidence creates edges between characters."""
    from unittest.mock import patch, MagicMock
    from novel_system.graph_name_policy import GraphProfile

    service = GraphService()

    mock_book_index = MagicMock()
    mock_book_index.corpora = {
        "character_card": [
            {"name": "韩立", "chapter": 1, "chapters": [1, 2], "text": "主角"},
            {"name": "南宫婉", "chapter": 2, "chapters": [2], "text": "女主"},
            {"name": "银月", "chapter": 3, "chapters": [3], "text": "配角"},
        ],
        "event_timeline": [
            # 韩立 and 南宫婉 share an event
            {"id": "e1", "chapter": 1, "title": "事件1", "description": "desc1", "participants": ["韩立", "南宫婉"]},
            # 银月 has own events, no shared events with 韩立
            {"id": "e2", "chapter": 3, "title": "事件2", "description": "desc2", "participants": ["银月"]},
        ],
        "character_registry": [{"name": "韩立"}, {"name": "南宫婉"}, {"name": "银月"}],
        # Relationship graph says 韩立/银月 are connected
        "relationship_graph": [
            {"title": "韩立/银月", "chapter": 3},
        ],
    }
    mock_book_index.vectorizers = {}
    mock_book_index.matrices = {}

    # Create a profile with all character names as seeds so they pass canonicalization
    test_profile = GraphProfile.default("test-book")
    test_profile.character_seeds = {"韩立", "南宫婉", "银月"}

    with patch.object(service, "ensure_indexed"), \
         patch.object(service.repo, "load", return_value=mock_book_index), \
         patch("novel_system.graph_service.is_book_in_whitelist", return_value=False), \
         patch("novel_system.graph_service.build_profile_from_character_registry", return_value=test_profile):
        from novel_system.models import Scope
        result = service.get_interactive_graph("test-book", Scope(chapters=[1, 3]), density="auto")

    # Check that there's a character_relation edge between 韩立 and 银月
    char_relation_edges = [
        e for e in result["edges"]
        if e["type"] == "character_relation"
        and ("韩立" in e["source"] and "银月" in e["target"])
        or ("银月" in e["source"] and "韩立" in e["target"])
    ]
    assert len(char_relation_edges) > 0, "Expected character_relation edge between 韩立 and 银月 from relationship_graph"
    assert char_relation_edges[0]["weight"] > 0
