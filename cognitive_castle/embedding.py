"""Embedding using sentence-transformers.

Produces 384-dim L2-normalised vectors (default: all-MiniLM-L6-v2, configurable
via ``embedder_model`` in config).

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
        from .config import CognitiveCastleConfig

        cfg = CognitiveCastleConfig()
    return cfg.embedder_model


def _is_cuda_oom(exc: BaseException) -> bool:
    """Detect CUDA out-of-memory errors by exception type or message.

    On shared dev machines the GPU may not have enough free VRAM when Castle
    loads the embedder. Without a fallback the entire mining pipeline fails.
    Match torch.cuda.OutOfMemoryError when available, then fall back to
    substring matching for environments where torch isn't importable.
    """
    try:
        import torch  # type: ignore
        if isinstance(exc, torch.cuda.OutOfMemoryError):
            return True
    except (ImportError, AttributeError):
        pass
    msg = str(exc).lower()
    return "out of memory" in msg or "cudaerrormemoryallocation" in msg


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

    try:
        model = SentenceTransformer(name, device=resolved)
    except Exception as e:
        if resolved == "cuda" and _is_cuda_oom(e):
            import sys
            print(
                f"[embedding] CUDA load failed ({type(e).__name__}: {e}); "
                f"falling back to CPU embedder",
                file=sys.stderr,
            )
            resolved = "cpu"
            cache_key = f"{name}@{resolved}"
            if cache_key in _model_cache:
                return _model_cache[cache_key]
            model = SentenceTransformer(name, device=resolved)
        else:
            raise

    # bge-m3 with CUDA triggers a >3-minute flash-attention CUDA kernel
    # compilation on first use (PyTorch 2.x SDPA).  The compiled kernel is
    # NOT cached between processes, so every cold start hangs.  Disabling
    # flash SDP and memory-efficient SDP forces PyTorch to use the math
    # backend, which requires no JIT compilation and adds <1ms overhead for
    # the short sequences Castle embeds.  This is a process-level flag so it
    # applies to all subsequent CUDA ops, but Castle only uses CUDA for this
    # model — no impact on other code paths.
    if resolved == "cuda":
        try:
            import torch

            torch.backends.cuda.enable_flash_sdp(False)
            torch.backends.cuda.enable_mem_efficient_sdp(False)
            logger.debug("Flash/MemEff SDP disabled to avoid first-run CUDA JIT hang")
        except Exception:
            pass  # non-fatal — worst case is a slow first encode

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
    """Thin wrapper with a callable embedding-function interface."""

    def __init__(self, device: str = "auto"):
        self._device = device

    @staticmethod
    def name() -> str:
        return "default"

    def __call__(self, texts: list[str]) -> list[list[float]]:
        return embed_texts(texts, self._device)


_WARNED: set = set()


def get_embedding_function(device: Optional[str] = None):
    """Return a callable embedding function for use with the LanceDB backend."""
    if device is None:
        try:
            from .config import CognitiveCastleConfig

            device = CognitiveCastleConfig().embedding_device
        except Exception:
            device = "auto"
    return _SentenceTransformerEF(device or "auto")


def describe_device(device: Optional[str] = None) -> str:
    if device is None:
        try:
            from .config import CognitiveCastleConfig

            device = CognitiveCastleConfig().embedding_device
        except Exception:
            device = "auto"
    return _resolve_device(device or "auto")
