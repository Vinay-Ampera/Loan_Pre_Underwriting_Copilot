"""Retrieval settings, loaded from data/rag/config.yaml."""

from functools import lru_cache

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import REPO_ROOT

CONFIG_PATH = REPO_ROOT / "data" / "rag" / "config.yaml"


class RagConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    embedding_model: str
    query_prefix: str
    reranker_model: str
    candidates: int = Field(gt=0)
    top_k: int = Field(gt=0)
    min_relevance: float = Field(ge=0, le=1)
    min_vector_similarity: float = Field(ge=-1, le=1)
    precedent_candidates: int = Field(gt=0)


@lru_cache
def load_rag_config() -> RagConfig:
    return RagConfig.model_validate(yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")))
