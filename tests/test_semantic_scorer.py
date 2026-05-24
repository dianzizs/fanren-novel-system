"""Tests for semantic scorer retrieval-hit text handling."""

from novel_system.semantic_scorer import SemanticScorer


class KeywordEmbeddingProvider:
    """Tiny deterministic embedding provider for semantic scorer tests."""

    def __init__(self):
        self.embedded_texts: list[str] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.embedded_texts.extend(texts)
        vectors = []
        for text in texts:
            text = text or ""
            vectors.append([
                1.0 if "韩立" in text else 0.0,
                1.0 if "测试" in text else 0.0,
                1.0 if "三叔" in text else 0.0,
            ])
        return vectors


def test_semantic_scorer_reads_retrieval_hit_document_text():
    """RetrievalHit stores evidence text under document['text'], not hit.text."""
    embedding_provider = KeywordEmbeddingProvider()
    scorer = SemanticScorer(embedding_provider=embedding_provider)
    hits = [
        {
            "target": "chapter_chunks",
            "score": 0.6,
            "document": {
                "id": "ch2-target",
                "chapter": 2,
                "text": "韩立参加七玄门测试，是因为三叔推举。",
            },
        }
    ]

    score, warning = scorer.compute_similarity_with_hits("韩立为什么参加测试", hits)

    assert warning is None
    assert "韩立参加七玄门测试，是因为三叔推举。" in embedding_provider.embedded_texts
    assert score > 0.5
