"""Drawer text normalization: strip fenced code blocks, truncate to
2000 tokens (bge-m3's effective limit). Applied before embedding (A,
B) and before LLM prompting (C)."""

from __future__ import annotations
import re
import tiktoken

_FENCE_PATTERN = re.compile(r"```[\s\S]*?```", re.MULTILINE)
_ENC = tiktoken.get_encoding("cl100k_base")


def strip_code_blocks(text: str) -> str:
    """Remove all triple-backtick fenced code blocks."""
    return _FENCE_PATTERN.sub("", text)


def truncate_to_tokens(text: str, max_tokens: int = 2000) -> str:
    """Truncate to at most max_tokens (cl100k_base tokenizer)."""
    tokens = _ENC.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return _ENC.decode(tokens[:max_tokens])


def normalize(text: str, max_tokens: int = 2000) -> str:
    """Strip code blocks, then truncate. Order matters: stripping
    first means truncation budget is spent on prose, not code."""
    return truncate_to_tokens(strip_code_blocks(text), max_tokens)
