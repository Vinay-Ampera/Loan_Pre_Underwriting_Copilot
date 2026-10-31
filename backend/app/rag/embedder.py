"""Local BGE-small embeddings (384-d, normalised) and the cross-encoder reranker.

Both models run from the pip venv on CPU; nothing here calls a cloud service. Models load on first
use so importing this module is cheap.
"""

import math
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from app.rag.config import load_rag_config

EMBEDDING_DIM = 384


def _load(factory: Callable[..., Any], name: str) -> Any:
    """Load from the local cache first (no network round trip); download only if it is missing."""
    try:
        return factory(name, device="cpu", local_files_only=True)
    except OSError:
        return factory(name, device="cpu")


@lru_cache
def _encoder() -> Any:
    from sentence_transformers import SentenceTransformer

    return _load(SentenceTransformer, load_rag_config().embedding_model)


@lru_cache
def _cross_encoder() -> Any:
    from sentence_transformers import CrossEncoder

    return _load(CrossEncoder, load_rag_config().reranker_model)


def embed_passages(texts: list[str]) -> list[list[float]]:
    """Embed clause or precedent text (no query prefix)."""
    if not texts:
        return []
    vecs = _encoder().encode(texts, normalize_embeddings=True, batch_size=32)
    return [[float(x) for x in v] for v in vecs]


def embed_query(query: str) -> list[float]:
    prefixed = load_rag_config().query_prefix + query
    vec = _encoder().encode([prefixed], normalize_embeddings=True)[0]
    return [float(x) for x in vec]


def rerank_scores(query: str, passages: list[str]) -> list[float]:
    """Relevance of each passage to the query, 0..1 (sigmoid of the cross-encoder logit)."""
    if not passages:
        return []
    logits = _cross_encoder().predict([(query, p) for p in passages])
    return [1.0 / (1.0 + math.exp(-float(x))) for x in logits]
