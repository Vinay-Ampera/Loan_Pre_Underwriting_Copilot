"""Run once while the image is built: load the local embedding, reranker and OCR models so they
are inside the image and a container never downloads a model at run time."""

import numpy as np

from app.intake.ocr import get_engine, read_image
from app.rag.embedder import embed_passages, embed_query, rerank_scores

vectors = embed_passages(["Applicants must be 21 to 55 years old at loan maturity."])
assert len(vectors[0]) == 384
embed_query("minimum age")
rerank_scores("minimum age", ["Applicants must be 21 to 55 years old."])
print("ocr engine:", type(get_engine()).__name__)
read_image(np.full((60, 200, 3), 255, dtype=np.uint8))  # a blank BGR page
print("local models ready")
