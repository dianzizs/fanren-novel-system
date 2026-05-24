"""Unit tests for GraphRAG features: caching, concurrency, NetworkX serialization, and hybrid graph-vector search."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import networkx as nx
import pytest

from novel_system.config import AppConfig
from novel_system.indexing import BookIndexRepository, LoadedBookIndex
from novel_system.search.orchestrator import SearchOrchestrator


@pytest.fixture
def temp_books_dir():
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_config(temp_books_dir):
    cfg = MagicMock(spec=AppConfig)
    cfg.books_dir = temp_books_dir
    cfg.data_dir = temp_books_dir
    cfg.vector_store_dir = temp_books_dir / "vectors"
    cfg.minimax_api_key = "test-key"
    cfg.minimax_base_url = "https://api.minimax.chat/v1"
    cfg.minimax_chat_model = "test-model"
    return cfg


def test_llm_cache_saves_and_loads(mock_config):
    """验证 LLM 提取结果会被正确写入本地文件缓存，并且第二次请求时能够从缓存中读取，不触发 LLM 调用。"""
    repo = BookIndexRepository(mock_config)
    repo._active_book_id = "test_book_1"
    
    # Mock LLM response
    mock_llm_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "characters": [
            {"name": "韩立", "aliases": ["二愣子"], "description": "主角"}
        ],
        "relationships": [
            {"source": "韩立", "target": "墨大夫", "description": "师徒"}
        ],
        "events": [
            {"description": "韩立拜师", "participants": ["韩立", "墨大夫"]}
        ]
    })
    mock_llm_client.enabled = True
    mock_llm_client.chat.return_value = mock_response
    
    with patch.object(BookIndexRepository, "llm", mock_llm_client):
        # 1. 第一次调用：缓存不存在，触发 LLM chat
        chunk_text = "韩立走进了神手谷，见到了墨大夫。"
        ext1 = repo._extract_structured_from_llm(chunk_text)
        
        assert ext1 is not None
        assert ext1.characters[0].name == "韩立"
        assert mock_llm_client.chat.call_count == 1

        # 验证本地缓存文件存在
        import hashlib
        chunk_hash = hashlib.md5(chunk_text.encode("utf-8")).hexdigest()
        cache_file = repo._book_dir("test_book_1") / ".llm_cache" / f"{chunk_hash}.json"
        assert cache_file.exists()

        # 2. 第二次调用：相同的 chunk_text，此时应直接命中缓存，LLM chat 调用次数仍为 1
        ext2 = repo._extract_structured_from_llm(chunk_text)
        assert ext2 is not None
        assert ext2.characters[0].name == "韩立"
        assert mock_llm_client.chat.call_count == 1  # 依然是 1，说明直接读取了缓存


def test_networkx_graph_creation_and_load(mock_config):
    """测试 build_from_txt 是否能够成功构建 NetworkX 并持久化为 graph.json，且 load() 能够正确载入。"""
    repo = BookIndexRepository(mock_config)
    book_id = "test_book_graph"
    title = "测试书目"
    
    # 创建临时的 txt 文件
    temp_txt = repo._book_dir(book_id) / "source.txt"
    repo._book_dir(book_id).mkdir(parents=True, exist_ok=True)
    temp_txt.write_text("第1章 拜师学艺\n韩立。墨大夫。在谷内修炼。\n\n第2章 张飞雨\n韩立。张飞雨。成了好友。", encoding="utf-8")
    
    # Mock LLM 预热缓存逻辑，避免触发真实的 LLM 请求
    with patch.object(BookIndexRepository, "prewarm_llm_extractions") as mock_prewarm:
        # 手动向 _active_llm_extractions 注入伪数据
        repo._active_llm_extractions = {}
        
        manifest = repo.build_from_txt(book_id, title, temp_txt)
        
        # 验证 graph.json 是否被写入
        graph_json_path = repo._book_dir(book_id) / "graph.json"
        assert graph_json_path.exists()
        
        # 验证 graph.json 的结构
        graph_data = json.loads(graph_json_path.read_text(encoding="utf-8"))
        assert "nodes" in graph_data
        assert "edges" in graph_data
        
        # 测试 load() 恢复 LoadedBookIndex 并附加 graph 对象
        loaded = repo.load(book_id)
        assert loaded.graph is not None
        assert isinstance(loaded.graph, nx.Graph)
        assert "韩立" in loaded.graph.nodes


def test_search_orchestrator_graphrag_retrieval():
    """测试 SearchOrchestrator 在有 Graph 附着时，能否匹配 Entity 并将 1-hop 邻居及边关系作为高分文档召回。"""
    orchestrator = SearchOrchestrator()
    
    # 构建包含 NetworkX 图谱的 Mock BookIndex
    class MockIndex(LoadedBookIndex):
        def __init__(self, G):
            self.manifest = {"id": "mock_book"}
            self.chapters = []
            self.corpora = {
                "character_card": [],
                "chapter_chunks": []
            }
            self.vectorizers = {}
            self.matrices = {}
            self.vector_stores = {}
            self.graph = G

    # 构建 NetworkX 测试图谱
    G = nx.Graph()
    G.add_node("韩立", first_chapter=1, aliases=["二愣子"])
    G.add_node("墨大夫", first_chapter=1, aliases=["墨居仁"])
    G.add_node("厉飞雨", first_chapter=2, aliases=[])
    G.add_edge("韩立", "墨大夫", weight=5, text="韩立和墨大夫是名义上的师徒，实际上勾心斗角。")
    G.add_edge("韩立", "厉飞雨", weight=3, text="韩立和厉飞雨是挚友，互相交易药丸。")
    
    index = MockIndex(G)
    
    # 执行检索：问题匹配了“韩立”，应同时召回韩立人物节点及其高权重边关系
    hits = orchestrator.retrieve(
        book_index=index,
        query="韩立的师父墨大夫对他做了什么",
        targets=["character_card"],
        chapter_scope=[1, 10],
        top_k=5
    )
    
    # 验证是否返回了图谱内容
    assert len(hits) >= 1
    
    # 查找是否有图谱节点/边被召回
    node_hits = [h for h in hits if h.document["id"] == "graph-node-韩立"]
    edge_hits = [h for h in hits if h.document["id"] == "graph-edge-韩立-墨大夫"]
    
    assert len(node_hits) == 1
    assert "二愣子" in node_hits[0].document["text"]
    
    assert len(edge_hits) == 1
    assert "勾心斗角" in edge_hits[0].document["text"]
