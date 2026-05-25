"""Test GraphRAG query router."""

from novel_system.graphrag_app.query_router import GraphRAGQueryRouter


def test_router_local_for_character_query():
    router = GraphRAGQueryRouter()
    mode = router.route("韩立是什么人物", requested_mode=None)
    assert mode == "local"


def test_router_global_for_theme_query():
    router = GraphRAGQueryRouter()
    mode = router.route("这本书的主题是什么", requested_mode=None)
    assert mode == "global"


def test_router_drift_for_cause_and_motive_query():
    router = GraphRAGQueryRouter()

    assert router.route("韩立为什么离开村子？", requested_mode=None) == "drift"
    assert router.route("墨大夫这样做的动机是什么？", requested_mode=None) == "drift"


def test_router_respects_requested_mode():
    router = GraphRAGQueryRouter()
    assert router.route("anything", requested_mode="global") == "global"
    assert router.route("anything", requested_mode="basic") == "basic"
    assert router.route("anything", requested_mode="drift") == "drift"
