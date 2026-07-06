"""Optional LOCAL semantic-similarity signal for ranking (Model2Vec).

The deterministic scorer (match/scorer.py) matches on keyword/skill OVERLAP — it
can't tell that "clinical informatics" and "health analytics leadership" are the
same field, or that a "Registered Nurse" posting is nothing like a data-analyst
resume even though both say "healthcare". This module adds a semantic layer:
cosine similarity between the candidate's profile text and a job's text, computed
LOCALLY with MinishLab's Model2Vec (a static, distilled embedding — numpy only, no
torch, ~30 MB, thousands of encodes/sec on one CPU core), MIT-licensed.

Design guarantees:
- **Fully optional + gated.** If the `model2vec` package or the model files aren't
  present, `available()` is False and every caller no-ops — the scorer stays
  byte-identical. It is also OFF by default (config.SEMANTIC_RANKING) so enabling
  it is an explicit, additive choice, never a silent change to existing scores.
- **Offline + distributable.** Loads a bundled model dir if present (for the exe),
  else the HF-cached model by name. No network at score time once cached.
- **Cheap + cached.** One process-wide model; per-text embeddings memoized by hash.

Public API: `available()`, `similarity(a, b) -> float in [0,1]`, `embed(texts)`.
"""
from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from pathlib import Path

import config

# Default model: small, permissive (MIT), numpy-only static embedding.
_MODEL_NAME = getattr(config, "SEMANTIC_MODEL", None) or "minishlab/potion-base-8M"
# Optional bundled model dir (for the frozen exe): data_static/models/<name>.
_BUNDLED_DIR = Path(config.__file__).resolve().parent / "data_static" / "models" / "potion-base-8M"

_model = None
_load_failed = False


def _enabled() -> bool:
    """Config gate. OFF unless SEMANTIC_RANKING is truthy (env or config), so the
    deterministic score is unchanged for anyone who hasn't opted in."""
    val = os.getenv("SEMANTIC_RANKING")
    if val is not None:
        return val.strip() not in ("", "0", "false", "False", "no")
    return bool(getattr(config, "SEMANTIC_RANKING", False))


def _resolve_source() -> str:
    """The path/id to load the model from, resolved WITHOUT touching the network.

    Prefer a bundled dir (frozen exe). Otherwise resolve the HF-cached snapshot by
    name using ``local_files_only`` — a concrete on-disk path that ``from_pretrained``
    loads directly (no HTTP round-trip). This upholds the module's "no network once
    cached" guarantee: the default ``StaticModel.from_pretrained(name)`` uses
    ``force_download=True`` and always calls ``snapshot_download`` online — even for a
    fully cached model — which fails/hangs whenever the hub is unreachable (and, in
    the test suite, trips the autouse socket guard). Falls back to the bare model id
    (network-capable, first-run download) only when nothing is cached locally."""
    if _BUNDLED_DIR.exists():
        return str(_BUNDLED_DIR)
    try:
        import huggingface_hub
        return huggingface_hub.snapshot_download(
            _MODEL_NAME, repo_type="model", local_files_only=True)
    except Exception:
        # Not cached (or hub layout changed): let from_pretrained download it.
        return _MODEL_NAME


def _load():
    """Lazily load the Model2Vec static model once. Returns the model or None if
    model2vec isn't installed / the model can't be loaded (then we no-op).

    The negative cache latches ONLY when the ``model2vec`` package is absent — a
    stable, permanent condition. A failed *model load* (e.g. a transient cache/IO
    hiccup) is NOT latched, so a later call can retry rather than being poisoned for
    the life of the process."""
    global _model, _load_failed
    if _model is not None or _load_failed:
        return _model
    try:
        from model2vec import StaticModel
    except Exception:
        _load_failed = True  # package missing -> permanent, safe to latch
        return None
    try:
        _model = StaticModel.from_pretrained(_resolve_source())
    except Exception:
        _model = None  # transient load failure: leave un-latched so it can retry
    return _model


def available() -> bool:
    """True only when semantic ranking is enabled AND the model actually loaded."""
    return _enabled() and _load() is not None


@lru_cache(maxsize=4096)
def _embed_one(text: str):
    """Cached unit-normalized embedding for one text (or None if unavailable)."""
    model = _load()
    if model is None:
        return None
    import numpy as np
    vec = model.encode([text[:4000] if text else ""])[0].astype("float32")
    norm = float(np.linalg.norm(vec))
    return vec / norm if norm > 0 else vec


def embed(texts):
    """Embed a list of texts -> list of numpy vectors (or None entries when the
    model is unavailable). Public for batch callers / tests."""
    return [_embed_one(t or "") for t in texts]


def _key(text: str) -> str:
    return hashlib.md5((text or "").encode("utf-8")).hexdigest()


def similarity(a: str, b: str) -> float | None:
    """Cosine similarity in [0,1] between two texts, or None when semantic ranking
    is unavailable (not enabled / model absent). Both texts empty -> None."""
    if not available():
        return None
    if not (a and a.strip()) or not (b and b.strip()):
        return None
    import numpy as np
    va, vb = _embed_one(a), _embed_one(b)
    if va is None or vb is None:
        return None
    # Unit-normalized vectors -> dot == cosine. Related job/resume text lands in
    # ~[0,0.7]; negative cosine means unrelated, so clamp to [0,1] as the signal.
    return max(0.0, min(1.0, float(np.dot(va, vb))))
