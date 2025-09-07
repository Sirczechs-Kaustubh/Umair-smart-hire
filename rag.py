import os
import math
from typing import List, Optional, Tuple

_EMBEDDER = None
_EMBEDDER_FAILED = False
_RERANKER = None
_RERANKER_FAILED = False

def _load_embedder():
    """Load an embeddings model with a strong default, fallback to a lightweight model."""
    global _EMBEDDER, _EMBEDDER_FAILED
    if _EMBEDDER is not None or _EMBEDDER_FAILED:
        return _EMBEDDER
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        # Preferred strong models first (set via env):
        # - 'mixedbread-ai/mxbai-embed-large-v1' (high quality)
        # - 'BAAI/bge-base-en-v1.5' (solid general-purpose)
        # Fallback: 'all-MiniLM-L6-v2' (fast + small)
        preferred = os.getenv('EMBEDDINGS_MODEL')
        tried = []
        candidates = [
            preferred,
            'BAAI/bge-base-en-v1.5',
            'all-MiniLM-L6-v2',
        ]
        for name in [c for c in candidates if c]:
            try:
                _EMBEDDER = SentenceTransformer(name)
                return _EMBEDDER
            except Exception:
                tried.append(name)
                _EMBEDDER = None
        _EMBEDDER_FAILED = True
        return None
    except Exception:
        _EMBEDDER_FAILED = True
        _EMBEDDER = None
        return None

def _load_reranker():
    """Optionally load a cross-encoder reranker. Controlled by USE_RERANKER env flag."""
    global _RERANKER, _RERANKER_FAILED
    if _RERANKER is not None or _RERANKER_FAILED:
        return _RERANKER
    if os.getenv('USE_RERANKER', '1') != '1':
        _RERANKER_FAILED = True
        return None
    try:
        from sentence_transformers import CrossEncoder  # type: ignore
        model_name = os.getenv('RERANKER_MODEL', 'cross-encoder/ms-marco-MiniLM-L-6-v2')
        _RERANKER = CrossEncoder(model_name)
        return _RERANKER
    except Exception:
        _RERANKER_FAILED = True
        _RERANKER = None
        return None

def embed_texts(texts: List[str]) -> Optional[List[List[float]]]:
    emb = _load_embedder()
    if not emb:
        return None
    try:
        # normalize to get cosine ~ dot product
        return emb.encode(texts, normalize_embeddings=True).tolist()
    except Exception:
        return None

def cosine(u: List[float], v: List[float]) -> float:
    # Both should be normalized by embedder; keep a safe fallback
    if not u or not v or len(u) != len(v):
        return 0.0
    s = sum(a*b for a,b in zip(u,v))
    # Clamp to [0,1]
    return max(0.0, min(1.0, s))

def _best_matches_embeddings(query: str, items: List[Tuple[str, str]], top_k: int = 10):
    embs = embed_texts([query] + [t for _, t in items])
    if not embs:
        return None
    qv = embs[0]
    out = []
    for (iid, txt), vec in zip(items, embs[1:]):
        out.append((iid, txt, cosine(qv, vec)))
    out.sort(key=lambda x: x[2], reverse=True)
    return out[:top_k]

def _best_matches_jaccard(query: str, items: List[Tuple[str, str]], top_k: int = 10):
    def tokset(t: str):
        return set(w.strip().lower() for w in t.split() if w.strip())
    qs = tokset(query)
    out = []
    for iid, txt in items:
        ts = tokset(txt)
        if not qs or not ts:
            sim = 0.0
        else:
            inter = len(qs & ts)
            union = len(qs | ts)
            sim = (inter / union) if union else 0.0
        out.append((iid, txt, sim))
    out.sort(key=lambda x: x[2], reverse=True)
    return out[:top_k]

def best_matches(query: str, items: List[Tuple[str, str]], top_k: int = 10) -> List[Tuple[str, str, float]]:
    """
    Rank items by semantic similarity to query using embeddings + optional reranker.
    - Uses the embeddings model indicated by EMBEDDINGS_MODEL (strong defaults + fallback).
    - If USE_RERANKER=1 and a CrossEncoder is available, reranks the top-N candidates.
    Returns list of (id, text, score) where score in [0,1].
    """
    if not items:
        return []

    preselect = max(top_k, int(os.getenv('RERANK_PRESELECT', '50')))
    preselect = min(preselect, len(items))

    # Phase 1: embedding similarity (or Jaccard fallback)
    emb_ranked = _best_matches_embeddings(query, items, top_k=preselect)
    if not emb_ranked:
        emb_ranked = _best_matches_jaccard(query, items, top_k=preselect)

    # Phase 2: optional CrossEncoder rerank
    reranker = _load_reranker()
    if reranker and emb_ranked and len(emb_ranked) >= 2:
        try:
            pairs = [(query, txt) for _, txt, _ in emb_ranked]
            scores = reranker.predict(pairs).tolist()  # type: ignore
            # Min-max scale to [0,1] for consistent downstream usage
            lo = min(scores)
            hi = max(scores)
            rng = (hi - lo) or 1.0
            rescored = []
            for (iid, txt, _), s in zip(emb_ranked, scores):
                rescored.append((iid, txt, (s - lo) / rng))
            rescored.sort(key=lambda x: x[2], reverse=True)
            return rescored[:top_k]
        except Exception:
            pass

    # No reranker or failed → use embedding/Jaccard scores
    return emb_ranked[:top_k]

def warmup(texts: Optional[List[str]] = None) -> int:
    """Load the embedder and encode a few texts to ensure model is ready.
    Returns the number of texts encoded.
    """
    emb = _load_embedder()
    if not emb:
        return 0
    if not texts:
        texts = ["warmup", "initialize embeddings", "smarthire"]
    try:
        # small batch to trigger model load and compilation if any
        emb.encode(texts[:16])
        return min(len(texts), 16)
    except Exception:
        return 0
