from __future__ import annotations
import logging
import hashlib
import json
import numpy as np
import pickle
from typing import Any, Optional, TYPE_CHECKING
from sklearn.feature_extraction.text import TfidfVectorizer
import jieba

from ..vector_store import FAISSVectorStore

if TYPE_CHECKING:
    from ..embedding.base import EmbeddingProvider
    from ..vector_store.base import BaseVectorStore
    from ..config import AppConfig

logger = logging.getLogger(__name__)

def tokenize_chinese(text: str) -> list[str]:
    """中文分词，用于 TF-IDF。"""
    return list(jieba.cut(text))

def build_vector_payload(docs: list[dict[str, Any]]) -> dict[str, Any]:
    """构建词级 TF-IDF 向量。"""
    texts = [doc.get("text", "") for doc in docs]
    if not any(texts):
        return {"vectorizer": None, "matrix": None}

    # 词级 TF-IDF
    vectorizer = TfidfVectorizer(
        tokenizer=tokenize_chinese,
        lowercase=False,
        min_df=1,
        max_features=50000,
        dtype=np.float32,
    )
    matrix = vectorizer.fit_transform(texts)
    return {"vectorizer": vectorizer, "matrix": matrix}

def build_faiss_index(
    docs: list[dict[str, Any]],
    embedding_provider: EmbeddingProvider,
) -> Optional[FAISSVectorStore]:
    """构建 FAISS 向量索引。"""
    if not docs:
        return None

    # 提取 ID 和文本
    ids = [doc.get("id", f"doc-{i}") for i, doc in enumerate(docs)]
    texts = [doc.get("text", "") for doc in docs]

    if not any(texts):
        logger.warning("All documents have empty text, skipping FAISS index")
        return None

    # 计算 embeddings
    try:
        embeddings = embedding_provider.embed(texts)
    except Exception as e:
        logger.warning(f"Failed to compute embeddings: {e}")
        return None

    if not embeddings:
        logger.warning("No embeddings generated, skipping FAISS index")
        return None

    # 获取向量维度
    dimension = len(embeddings[0])

    # 创建 FAISS 索引
    vector_store = FAISSVectorStore(dimension=dimension, metric="ip")
    vector_store.add(ids=ids, vectors=embeddings, documents=docs)

    logger.info(f"Built FAISS index with {len(ids)} vectors, dimension={dimension}")
    return vector_store

def build_vector_indexes(
    book_id: str,
    corpora: dict[str, list[dict[str, Any]]],
    config: AppConfig,
    embedding_provider: Optional[EmbeddingProvider] = None,
) -> bool:
    """为所有 corpus 构建并保存 FAISS 向量索引。"""
    has_vector_index = False
    if embedding_provider is None:
        return has_vector_index
    book_hash = hashlib.md5(book_id.encode()).hexdigest()[:12]
    vectors_dir = config.vector_store_dir / book_hash
    vectors_dir.mkdir(parents=True, exist_ok=True)
    for name, docs in corpora.items():
        if not docs:
            continue
        try:
            vector_store = build_faiss_index(docs, embedding_provider)
            if vector_store is not None:
                corpus_vector_dir = vectors_dir / name
                corpus_vector_dir.mkdir(parents=True, exist_ok=True)
                vector_store.save(str(corpus_vector_dir))
                has_vector_index = True
                logger.info(f"Saved vector index for {name} to {corpus_vector_dir}")
        except Exception as e:
            logger.warning(f"Failed to build vector index for {name}: {e}")
    return has_vector_index

def load_vector_stores(book_id: str, config: AppConfig) -> dict[str, BaseVectorStore]:
    """加载向量索引（使用配置的向量存储目录）。"""
    vector_stores: dict[str, BaseVectorStore] = {}
    book_hash = hashlib.md5(book_id.encode()).hexdigest()[:12]
    vectors_dir = config.vector_store_dir / book_hash
    if vectors_dir.exists() and vectors_dir.is_dir():
        for corpus_dir in vectors_dir.iterdir():
            if not corpus_dir.is_dir():
                continue
            corpus_name = corpus_dir.name
            try:
                # 从 metadata.json 读取维度信息
                metadata_path = corpus_dir / "metadata.json"
                if not metadata_path.exists():
                    continue
                with metadata_path.open("r", encoding="utf-8") as f:
                    metadata = json.load(f)
                dimension = metadata.get("dimension", 512)
                metric = metadata.get("metric", "ip")

                # 创建并加载 FAISS 索引
                vector_store = FAISSVectorStore(dimension=dimension, metric=metric)
                vector_store.load(str(corpus_dir))
                vector_stores[corpus_name] = vector_store
                logger.info(f"Loaded vector index for {corpus_name}")
            except Exception as e:
                logger.warning(f"Failed to load vector index for {corpus_name}: {e}")
    return vector_stores
