"""Fake embedder and reranker so RAG tests run without downloading or running the models."""

import hashlib
import math
import re

from app.rag.embedder import EMBEDDING_DIM


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def fake_vector(text: str) -> list[float]:
    """Bag-of-words hashed into 384 dimensions, unit length: texts sharing words are close."""
    vec = [0.0] * EMBEDDING_DIM
    for w in _words(text):
        vec[int(hashlib.md5(w.encode()).hexdigest(), 16) % EMBEDDING_DIM] += 1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def fake_embed_passages(texts: list[str]) -> list[list[float]]:
    return [fake_vector(t) for t in texts]


def fake_rerank(query: str, passages: list[str]) -> list[float]:
    q = set(_words(query))
    return [len(q & set(_words(p))) / (len(q) or 1) for p in passages]
