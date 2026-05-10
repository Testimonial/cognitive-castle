"""Embedding using sentence-transformers (replaces ChromaDB ONNX dependency).

Produces the same all-MiniLM-L6-v2 model and 384-dim L2-normalised vectors
as the ChromaDB default, so the switch is transparent to callers.

Supported hardware (env ``CASTLE_EMBEDDING_DEVICE`` or config key):
  auto   — prefer MPS ▸ CUDA ▸ CPU
  cpu    — force CPU
  cuda   — NVIDIA via PyTorch CUDA
  mps    — Apple Silicon via Metal
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

EMBED_DIM = 384

_model_cache: dict = {}


def _resolve_model_name(cfg=None) -> str:
    """Return the embedder model name from config (with default fallback)."""
    if cfg is None:
        from .config import MempalaceConfig

        cfg = MempalaceConfig()
    return cfg.embedder_model


def _get_model(device: str = "auto", cfg=None):
    name = _resolve_model_name(cfg)
    resolved = _resolve_device(device)
    cache_key = f"{name}@{resolved}"
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise RuntimeError(
            "sentence-transformers is required: pip install sentence-transformers"
        )

    model = SentenceTransformer(name, device=resolved)
    _model_cache[cache_key] = model
    logger.info("Embedding model loaded (device=%s → %s)", device, resolved)
    return model


def _resolve_device(device: str) -> str:
    if device == "auto":
        try:
            import torch

            if torch.backends.mps.is_available():
                return "mps"
            if torch.cuda.is_available():
                return "cuda"
        except ImportError:
            pass
        return "cpu"
    return device


def embed_texts(texts: list[str], device: str = "auto") -> list[list[float]]:
    """Embed a list of strings. Returns a list of 384-dim float lists."""
    model = _get_model(device)
    vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return vecs.tolist()


class _SentenceTransformerEF:
    """Thin wrapper with a ChromaDB-compatible callable interface."""

    def __init__(self, device: str = "auto"):
        self._device = device

    @staticmethod
    def name() -> str:
        return "default"

    def __call__(self, texts: list[str]) -> list[list[float]]:
        return embed_texts(texts, self._device)


_WARNED: set = set()


def get_embedding_function(device: Optional[str] = None):
    """Return a callable embedding function compatible with the ChromaDB EF contract."""
    if device is None:
        try:
            from .config import MempalaceConfig

            device = MempalaceConfig().embedding_device
        except Exception:
            device = "auto"
    return _SentenceTransformerEF(device or "auto")


def describe_device(device: Optional[str] = None) -> str:
    if device is None:
        try:
            from .config import MempalaceConfig

            device = MempalaceConfig().embedding_device
        except Exception:
            device = "auto"
    return _resolve_device(device or "auto")
