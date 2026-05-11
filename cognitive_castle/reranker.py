"""reranker.py — Cross-encoder reranker wrapper.

Lazy-loaded singleton. Device-aware: picks the GPU model on CUDA, the smaller
CPU-friendly model otherwise. Public entry point `rerank` returns scores
aligned to the input candidate order.
"""
from __future__ import annotations

from typing import Optional

# Cached model instance, keyed by (model_name, device).
_model_cache: dict[tuple[str, str], object] = {}


def _cuda_available() -> bool:
    """Return True if a CUDA device is available. Isolated for test mocking."""
    try:
        import torch  # type: ignore
        return torch.cuda.is_available()
    except Exception:
        return False


def _resolve_device(device: str = "auto") -> str:
    if device == "auto":
        return "cuda" if _cuda_available() else "cpu"
    if device not in ("cuda", "cpu"):
        raise ValueError(f"device must be 'auto', 'cuda', or 'cpu'; got {device!r}")
    return device


def _pick_model_for_device(device: str, cfg) -> str:
    if device == "cuda":
        return cfg.reranker_model_gpu
    return cfg.reranker_model_cpu


def _get_reranker(model_name: str, device: str):
    """Lazy-load and cache the CrossEncoder for (model_name, device)."""
    key = (model_name, device)
    if key not in _model_cache:
        from sentence_transformers import CrossEncoder  # local import keeps test mocking simple
        _model_cache[key] = CrossEncoder(model_name, device=device)
    return _model_cache[key]


def rerank(
    query: str,
    candidates: list[str],
    device: str = "auto",
    cfg: Optional[object] = None,
) -> list[float]:
    """Score (query, candidate) pairs with the device-appropriate cross-encoder.

    Returns scores aligned to the input candidate order. Empty input returns
    an empty list without loading the model.
    """
    if not candidates:
        return []
    if cfg is None:
        from .config import CognitiveCastleConfig
        cfg = CognitiveCastleConfig()
    resolved_device = _resolve_device(device)
    model_name = _pick_model_for_device(resolved_device, cfg)
    model = _get_reranker(model_name, resolved_device)
    pairs = [(query, doc) for doc in candidates]
    raw_scores = model.predict(pairs)
    return [float(s) for s in raw_scores]


def clear_cache() -> None:
    """Drop cached model instances. Useful for tests."""
    _model_cache.clear()
