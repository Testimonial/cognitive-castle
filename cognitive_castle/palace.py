"""
palace.py — Shared palace operations.

Consolidates collection access patterns used by both miners and the MCP server.
"""

import contextlib
import hashlib
import os
import re

from .backends.lancedb_backend import LanceDBBackend

SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    ".next",
    "coverage",
    ".castle",
    ".ruff_cache",
    ".mypy_cache",
    ".pytest_cache",
    ".cache",
    ".tox",
    ".nox",
    ".idea",
    ".vscode",
    ".ipynb_checkpoints",
    ".eggs",
    "htmlcov",
    "target",
}

_DEFAULT_BACKEND = LanceDBBackend()

# A normalization upgrade appends a fresh source revision; prior drawers stay
# available. Completion metadata distinguishes a finished import from a crash.
NORMALIZE_VERSION = 3  # lossless chunks and append-only source revisions


def source_signature(source_file: str) -> dict:
    """Capture the file state before reading; growing files remain eligible on retry."""
    stat = os.stat(source_file)
    return {"source_mtime_ns": stat.st_mtime_ns, "source_size": stat.st_size}


def source_revision(content: str, mode: str = "project") -> str:
    """Stable revision key makes interrupted writes retryable without overwriting history."""
    return hashlib.sha256(f"{NORMALIZE_VERSION}:{mode}:{content}".encode()).hexdigest()[:24]


def revision_drawer_id(source_file: str, wing: str, room: str, revision: str, index: int) -> str:
    key = hashlib.sha256(f"{source_file}:{revision}:{index}".encode()).hexdigest()[:24]
    return f"drawer_{wing}_{room}_{key}"


def split_verbatim(content: str, size: int = 800) -> list:
    """Partition text into bounded, exact slices, including whitespace and short tails."""
    chunks = []
    start = 0
    while start < len(content):
        end = min(start + size, len(content))
        if end < len(content):
            boundary = content.rfind("\n", start, end)
            if boundary >= start + size // 2:
                end = boundary + 1
        chunks.append({"content": content[start:end], "chunk_index": len(chunks)})
        start = end
    return chunks


def get_collection(
    palace_path: str,
    collection_name: str = "castle_drawers",
    create: bool = True,
):
    """Get the palace collection through the backend layer."""
    return _DEFAULT_BACKEND.get_collection(
        palace_path,
        collection_name=collection_name,
        create=create,
    )


def get_closets_collection(palace_path: str, create: bool = True):
    """Get the closets collection — the searchable index layer."""
    return get_collection(palace_path, collection_name="castle_closets", create=create)


CLOSET_CHAR_LIMIT = 1500  # fill closet until ~1500 chars, then start a new one
CLOSET_EXTRACT_WINDOW = 5000  # how many chars of source content to scan for entities/topics

# Common capitalized words that look like proper nouns but are usually
# sentence-starters or filler. Filtered out of entity extraction.
_ENTITY_STOPLIST = frozenset(
    {
        "The",
        "This",
        "That",
        "These",
        "Those",
        "When",
        "Where",
        "What",
        "Why",
        "Who",
        "Which",
        "How",
        "After",
        "Before",
        "Then",
        "Now",
        "Here",
        "There",
        "And",
        "But",
        "Or",
        "Yet",
        "So",
        "If",
        "Else",
        "Yes",
        "No",
        "Maybe",
        "Okay",
        "User",
        "Assistant",
        "System",
        "Tool",
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    }
)


_CANDIDATE_RX_CACHE = None


def _candidate_entity_words(text: str) -> list:
    """Find entity candidate words using i18n-aware patterns.

    Uses the same candidate_patterns as entity_detector (loaded from locale
    JSON files via get_entity_patterns), so non-Latin names (Cyrillic,
    accented Latin, etc.) are detected alongside ASCII names.
    """
    global _CANDIDATE_RX_CACHE
    if _CANDIDATE_RX_CACHE is None:
        from .config import CognitiveCastleConfig
        from .i18n import get_entity_patterns

        patterns = get_entity_patterns(CognitiveCastleConfig().entity_languages)
        rxs = []
        for pat in patterns["candidate_patterns"]:
            try:
                rxs.append(re.compile(pat))
            except re.error:
                continue
        _CANDIDATE_RX_CACHE = rxs
    words = []
    for rx in _CANDIDATE_RX_CACHE:
        words.extend(rx.findall(text))
    return words


def build_closet_lines(source_file, drawer_ids, content, wing, room):
    """Build compact closet pointer lines from drawer content.

    Returns a LIST of lines (not joined). Each line is one complete topic
    pointer — never split across closets.

    Format: topic|entities|→drawer_ids
    """
    import re
    from pathlib import Path

    drawer_ref = ",".join(drawer_ids[:3])
    window = content[:CLOSET_EXTRACT_WINDOW]

    # Extract proper nouns (2+ occurrences). Uses i18n-aware patterns so
    # non-Latin names (Cyrillic, accented Latin, etc.) are also detected.
    words = _candidate_entity_words(window)
    word_freq = {}
    for w in words:
        if w in _ENTITY_STOPLIST:
            continue
        word_freq[w] = word_freq.get(w, 0) + 1
    entities = sorted(
        [w for w, c in word_freq.items() if c >= 2],
        key=lambda w: -word_freq[w],
    )[:5]
    entity_str = ";".join(entities) if entities else ""

    # Extract key phrases — action verbs + context
    topics = []
    for pattern in [
        r"(?:built|fixed|wrote|added|pushed|tested|created|decided|migrated|reviewed|deployed|configured|removed|updated)\s+[\w\s]{3,40}",
    ]:
        topics.extend(re.findall(pattern, window, re.IGNORECASE))
    # Also grab section headers if present
    for header in re.findall(r"^#{1,3}\s+(.{5,60})$", window, re.MULTILINE):
        topics.append(header.strip())
    # Dedupe preserving order
    topics = list(dict.fromkeys(t.strip().lower() for t in topics))[:12]

    # Extract quotes
    quotes = re.findall(r'"([^"]{15,150})"', window)

    # Build pointer lines — each one is atomic, never split
    lines = []
    for topic in topics:
        lines.append(f"{topic}|{entity_str}|→{drawer_ref}")
    for quote in quotes[:3]:
        lines.append(f'"{quote}"|{entity_str}|→{drawer_ref}')

    # Always have at least one line
    if not lines:
        name = Path(source_file).stem[:40]
        lines.append(f"{wing}/{room}/{name}|{entity_str}|→{drawer_ref}")

    return lines


def purge_file_closets(closets_col, source_file: str) -> None:
    """Delete every closet associated with ``source_file``.

    Explicit maintenance operation. Normal ingestion preserves historical
    closets and must not call this helper.
    """
    try:
        closets_col.delete(where={"source_file": source_file})
    except Exception:
        pass


def upsert_closet_lines(closets_col, closet_id_base, lines, metadata):
    """Write topic lines to closets, packed greedily without splitting a line.

    Closets are deterministically numbered (``..._01``, ``..._02``, …) and
    each ``upsert`` retries the same revision at that ID. Callers include
    the source revision in ``closet_id_base`` to preserve historical pointers.

    Returns the number of closets written.
    """
    closet_num = 1
    current_lines: list = []
    current_chars = 0
    closets_written = 0

    def _flush():
        nonlocal closets_written
        if not current_lines:
            return
        closet_id = f"{closet_id_base}_{closet_num:02d}"
        text = "\n".join(current_lines)
        closets_col.upsert(documents=[text], ids=[closet_id], metadatas=[metadata])
        closets_written += 1

    for line in lines:
        line_len = len(line)
        # Would this line fit whole in the current closet?
        if current_chars > 0 and current_chars + line_len + 1 > CLOSET_CHAR_LIMIT:
            _flush()
            closet_num += 1
            current_lines = []
            current_chars = 0

        current_lines.append(line)
        current_chars += line_len + 1  # +1 for newline

    _flush()
    return closets_written


@contextlib.contextmanager
def mine_lock(source_file: str):
    """Cross-platform file lock for mine operations.

    Prevents simultaneous imports of the same source from interleaving batches
    and completion markers.
    """
    lock_dir = os.path.join(os.path.expanduser("~"), ".castle", "locks")
    os.makedirs(lock_dir, exist_ok=True)
    lock_path = os.path.join(
        lock_dir, hashlib.sha256(source_file.encode()).hexdigest()[:16] + ".lock"
    )

    lf = open(lock_path, "w")
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lf.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(lf, fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lf.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(lf, fcntl.LOCK_UN)
        except Exception:
            pass
        lf.close()


class MineAlreadyRunning(RuntimeError):
    """Raised when another `castle mine` already holds the per-palace lock."""


@contextlib.contextmanager
def mine_palace_lock(palace_path: str):
    """Per-palace non-blocking lock around the full `mine` pipeline.

    The per-file `mine_lock` serializes writes for a single source;
    it does not prevent N copies of `castle mine <dir>`
    from being spawned concurrently by hooks. When that happens, each copy
    drives vector inserts in parallel against the same palace,
    which can corrupt the index and produce unexpected blowups.

    The lock file is keyed by sha256(palace_path) so mines against
    *different* palaces can still run in parallel — we only serialize
    writes into the same palace, which is the correctness boundary.

    The key is derived from a fully normalized form of the path:
    `realpath` resolves symlinks and `..` segments, and `normcase` folds
    case on Windows (which has a case-insensitive filesystem). Without
    normcase, `C:\\Palace` and `c:\\palace` would hash to different keys
    on Windows and let two concurrent mines touch the same on-disk palace.

    Non-blocking: if another `castle mine` is already writing to this palace,
    raise MineAlreadyRunning so the caller can exit cleanly instead of
    piling up as a waiting worker.
    """
    lock_dir = os.path.join(os.path.expanduser("~"), ".castle", "locks")
    os.makedirs(lock_dir, exist_ok=True)
    resolved = os.path.realpath(os.path.expanduser(palace_path))
    lock_key_source = os.path.normcase(resolved)
    palace_key = hashlib.sha256(lock_key_source.encode()).hexdigest()[:16]
    lock_path = os.path.join(lock_dir, f"mine_palace_{palace_key}.lock")

    lf = open(lock_path, "w")
    acquired = False
    try:
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(lf.fileno(), msvcrt.LK_NBLCK, 1)
                acquired = True
            except OSError as exc:
                raise MineAlreadyRunning(
                    f"another `castle mine` is already running against {resolved}"
                ) from exc
        else:
            import fcntl

            try:
                fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except BlockingIOError as exc:
                raise MineAlreadyRunning(
                    f"another `castle mine` is already running against {resolved}"
                ) from exc
        yield
    finally:
        if acquired:
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(lf.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(lf, fcntl.LOCK_UN)
            except Exception:
                pass
        lf.close()


# Backward-compatible alias (previous patch iteration used a single global
# lock). Kept so third-party callers that imported it continue to work; new
# code should use `mine_palace_lock(palace_path)` for per-palace scoping.
mine_global_lock = mine_palace_lock


def get_lock_dir() -> str:
    """Return the path to the castle lock directory (creates it if needed)."""
    lock_dir = os.path.join(os.path.expanduser("~"), ".castle", "locks")
    os.makedirs(lock_dir, exist_ok=True)
    return lock_dir


def clean_stale_locks(lock_dir: str, max_age_seconds: int = 86400) -> tuple[int, int]:
    """Delete lock files older than max_age_seconds. Returns (removed, kept)."""
    import time

    if not os.path.isdir(lock_dir):
        return 0, 0
    cutoff = time.time() - max_age_seconds
    removed = kept = 0
    for entry in os.scandir(lock_dir):
        if not entry.name.endswith(".lock"):
            continue
        try:
            mtime = entry.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            try:
                os.remove(entry.path)
                removed += 1
            except OSError:
                kept += 1
        else:
            kept += 1
    return removed, kept


def file_already_mined(collection, source_file: str, check_mtime: bool = False) -> bool:
    """Return whether a complete, current-schema revision has been filed.

    Both miners use ``check_mtime=True`` to compare nanosecond mtime and size.
    The default retains the existence-only contract for external callers.
    Older metadata with no revision key keeps its legacy mtime check.
    Paginate so a large or partially imported source cannot hide completion.
    """
    try:
        signature = source_signature(source_file) if check_mtime else None
        offset = 0
        while True:
            results = collection.get(
                where={"source_file": source_file},
                include=["metadatas"],
                limit=1000,
                offset=offset,
            )
            for meta in results.get("metadatas", []):
                meta = meta or {}
                if meta.get("normalize_version", 1) < NORMALIZE_VERSION:
                    continue
                if "source_revision" in meta:
                    if not meta.get("ingest_complete"):
                        continue
                    if signature is None or all(meta.get(k) == v for k, v in signature.items()):
                        return True
                elif not check_mtime:
                    return True
                elif meta.get("source_mtime") is not None:
                    if abs(float(meta["source_mtime"]) - os.path.getmtime(source_file)) < 0.001:
                        return True
            count = len(results.get("ids", []))
            if count < 1000:
                return False
            offset += count
    except (OSError, TypeError, ValueError):
        return False
