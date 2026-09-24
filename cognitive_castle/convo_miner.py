#!/usr/bin/env python3
"""
convo_miner.py — Mine conversations into the palace.

Ingests chat exports (Claude Code, ChatGPT, Slack, plain text transcripts).
Normalizes format, chunks by exchange pair (Q+A = one unit), files to palace.

Same palace as project mining. Different ingest strategy.
"""

import os
import sys
import hashlib
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

from .normalize import normalize
from .palace import (
    NORMALIZE_VERSION,
    SKIP_DIRS,
    file_already_mined,
    get_collection,
    mine_lock,
    revision_drawer_id,
    source_revision,
    source_signature,
    split_verbatim,
)


# Cached hall keywords — avoids re-reading config per drawer
_HALL_KEYWORDS_CACHE = None


def _detect_hall_cached(content: str) -> str:
    """Route content to a hall using cached keywords. Same logic as miner.detect_hall."""
    global _HALL_KEYWORDS_CACHE
    if _HALL_KEYWORDS_CACHE is None:
        from .config import CognitiveCastleConfig

        _HALL_KEYWORDS_CACHE = CognitiveCastleConfig().hall_keywords
    content_lower = content[:3000].lower()
    scores = {}
    for hall, keywords in _HALL_KEYWORDS_CACHE.items():
        score = sum(1 for kw in keywords if kw in content_lower)
        if score > 0:
            scores[hall] = score
    return max(scores, key=scores.get) if scores else "general"


# File types that might contain conversations
CONVO_EXTENSIONS = {
    ".txt",
    ".md",
    ".json",
    ".jsonl",
}

MIN_CHUNK_SIZE = 30  # legacy export; no longer a storage cutoff
CHUNK_SIZE = 800  # chars per drawer — align with miner.py
DRAWER_UPSERT_BATCH_SIZE = 1000
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB — skip files larger than this.
# Matches miner.py at 500 MB. Long Claude Code sessions, multi-year
# ChatGPT exports, and lifetime Slack dumps routinely exceed 10 MB; the
# cap at that level silently dropped them with `continue`. Per-drawer
# size is bounded by CHUNK_SIZE, but larger source files still produce
# more drawers and therefore more embedding/storage work — and content
# is normalized and loaded fully into memory before chunking, so memory
# use also scales with source size.


def _register_file(collection, source_file: str, wing: str, agent: str, signature=None):
    """Write a sentinel so file_already_mined() returns True for 0-chunk files.

    Without this, files that normalize to nothing or produce zero chunks are
    re-read and re-processed on every mine run because nothing was written to
    the palace on the first pass.
    """
    signature = signature if signature is not None else source_signature(source_file)
    sentinel_id = f"_reg_{hashlib.sha256(source_file.encode()).hexdigest()[:24]}"
    collection.upsert(
        documents=[f"[registry] {source_file}"],
        ids=[sentinel_id],
        metadatas=[
            {
                "wing": wing,
                "room": "_registry",
                "source_file": source_file,
                "added_by": agent,
                "filed_at": datetime.now().isoformat(),
                "ingest_mode": "registry",
                **signature,
                "source_revision": "empty",
                "ingest_complete": True,
                "normalize_version": NORMALIZE_VERSION,
            }
        ],
    )


# =============================================================================
# CHUNKING — exchange pairs for conversations
# =============================================================================


def chunk_exchanges(content: str) -> list:
    """Split on exchange boundaries without altering or dropping any source text."""
    starts = [m.start() for m in re.finditer(r"(?m)^>[ \t]?", content)]
    boundaries = sorted({0, *starts, len(content)})
    chunks = []
    for start, end in zip(boundaries, boundaries[1:]):
        for chunk in split_verbatim(content[start:end], CHUNK_SIZE):
            chunk["chunk_index"] = len(chunks)
            chunks.append(chunk)
    return chunks


def _chunk_by_exchange(lines: list) -> list:
    return chunk_exchanges("\n".join(lines))


def _chunk_by_paragraph(content: str) -> list:
    return split_verbatim(content, CHUNK_SIZE)


# =============================================================================
# ROOM DETECTION — topic-based for conversations
# =============================================================================

TOPIC_KEYWORDS = {
    "technical": [
        "code",
        "python",
        "function",
        "bug",
        "error",
        "api",
        "database",
        "server",
        "deploy",
        "git",
        "test",
        "debug",
        "refactor",
    ],
    "architecture": [
        "architecture",
        "design",
        "pattern",
        "structure",
        "schema",
        "interface",
        "module",
        "component",
        "service",
        "layer",
    ],
    "planning": [
        "plan",
        "roadmap",
        "milestone",
        "deadline",
        "priority",
        "sprint",
        "backlog",
        "scope",
        "requirement",
        "spec",
    ],
    "decisions": [
        "decided",
        "chose",
        "picked",
        "switched",
        "migrated",
        "replaced",
        "trade-off",
        "alternative",
        "option",
        "approach",
    ],
    "problems": [
        "problem",
        "issue",
        "broken",
        "failed",
        "crash",
        "stuck",
        "workaround",
        "fix",
        "solved",
        "resolved",
    ],
}


def detect_convo_room(content: str) -> str:
    """Score conversation content against topic keywords."""
    content_lower = content[:3000].lower()
    scores = {}
    for room, keywords in TOPIC_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in content_lower)
        if score > 0:
            scores[room] = score
    if scores:
        return max(scores, key=scores.get)
    return "general"


# =============================================================================
# PALACE OPERATIONS
# =============================================================================


# =============================================================================
# SCAN FOR CONVERSATION FILES
# =============================================================================


def scan_convos(convo_dir: str) -> list:
    """Find conversation files, or select exactly one explicitly supplied transcript."""
    source = Path(convo_dir).expanduser()
    if source.is_symlink():
        return []
    convo_path = source.resolve()
    if convo_path.is_file():
        if (
            convo_path.suffix.lower() in CONVO_EXTENSIONS
            and not convo_path.name.endswith(".meta.json")
            and convo_path.stat().st_size <= MAX_FILE_SIZE
        ):
            return [convo_path]
        return []
    files = []
    for root, dirs, filenames in os.walk(convo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for filename in filenames:
            if filename.endswith(".meta.json"):
                continue
            filepath = Path(root) / filename
            if filepath.suffix.lower() in CONVO_EXTENSIONS:
                # Skip symlinks and oversized files
                if filepath.is_symlink():
                    continue
                try:
                    if filepath.stat().st_size > MAX_FILE_SIZE:
                        continue
                except OSError:
                    continue
                files.append(filepath)
    return files


# =============================================================================
# MINE CONVERSATIONS
# =============================================================================


def _file_chunks_locked(
    collection, source_file, chunks, wing, room, agent, extract_mode, signature=None, revision=None
):
    """Append an idempotent source revision, marking completion after all batches.

    Historical drawers are never removed. Returns
    (drawers_added, room_counts_delta, skipped).
    """
    signature = signature if signature is not None else source_signature(source_file)
    revision = revision or source_revision("".join(c["content"] for c in chunks), extract_mode)
    room_counts_delta: dict = defaultdict(int)
    drawers_added = 0
    with mine_lock(source_file):
        # Re-check after lock — another agent may have just finished this file
        # at the current schema. Interrupted revisions remain eligible.
        if file_already_mined(collection, source_file, check_mtime=True):
            return 0, room_counts_delta, True

        # Batch chunks into bounded upserts so large transcripts keep most of
        # the embedding speedup without one huge Chroma/SQLite request. Keep
        # one filed_at per source file so all transcript drawers share an
        # ingest timestamp.
        filed_at = datetime.now().isoformat()
        for batch_start in range(0, len(chunks), DRAWER_UPSERT_BATCH_SIZE):
            batch_docs: list = []
            batch_ids: list = []
            batch_metas: list = []
            for chunk in chunks[batch_start : batch_start + DRAWER_UPSERT_BATCH_SIZE]:
                chunk_room = chunk.get("memory_type", room) if extract_mode == "general" else room
                if extract_mode == "general":
                    room_counts_delta[chunk_room] += 1
                drawer_id = revision_drawer_id(
                    source_file, wing, chunk_room, revision, chunk["chunk_index"]
                )
                batch_docs.append(chunk["content"])
                batch_ids.append(drawer_id)
                batch_metas.append(
                    {
                        "wing": wing,
                        "room": chunk_room,
                        "hall": _detect_hall_cached(chunk["content"]),
                        "source_file": source_file,
                        "chunk_index": chunk["chunk_index"],
                        "added_by": agent,
                        "filed_at": filed_at,
                        "ingest_mode": "convos",
                        "extract_mode": extract_mode,
                        **signature,
                        "source_revision": revision,
                        "ingest_complete": False,
                        "normalize_version": NORMALIZE_VERSION,
                    }
                )
            collection.upsert(documents=batch_docs, ids=batch_ids, metadatas=batch_metas)
            drawers_added += len(batch_docs)
        if chunks:
            collection.update(ids=[batch_ids[-1]], metadatas=[{"ingest_complete": True}])
    return drawers_added, room_counts_delta, False


def mine_convos(
    convo_dir: str,
    palace_path: str,
    wing: str = None,
    agent: str = "cognitive-castle",
    limit: int = 0,
    dry_run: bool = False,
    extract_mode: str = "exchange",
):
    """Mine a directory of conversation files into the palace.

    extract_mode:
        "exchange" — default exchange-pair chunking (Q+A = one unit)
        "general"  — general extractor: decisions, preferences, milestones, problems, emotions
    """

    convo_path = Path(convo_dir).expanduser().resolve()
    if not wing:
        from .config import normalize_wing_name

        wing = normalize_wing_name(convo_path.name)

    files = scan_convos(convo_dir)
    if limit > 0:
        files = files[:limit]

    print(f"\n{'=' * 55}")
    print("  Cognitive Castle Mine — Conversations")
    print(f"{'=' * 55}")
    print(f"  Wing:    {wing}")
    print(f"  Source:  {convo_path}")
    print(f"  Files:   {len(files)}")
    print(f"  Palace:  {palace_path}")
    if dry_run:
        print("  DRY RUN — nothing will be filed")
    print(f"{'-' * 55}\n")

    collection = get_collection(palace_path) if not dry_run else None

    total_drawers = 0
    files_skipped = 0
    room_counts = defaultdict(int)

    for i, filepath in enumerate(files, 1):
        source_file = str(filepath)

        # Skip if already filed
        if not dry_run and file_already_mined(collection, source_file, check_mtime=True):
            files_skipped += 1
            continue

        # Normalize format
        try:
            signature = source_signature(source_file)
            content = normalize(str(filepath))
        except (OSError, ValueError):
            # A transient read/parse failure must remain eligible for retry.
            continue

        if not content:
            if not dry_run:
                _register_file(collection, source_file, wing, agent, signature)
            continue

        # Chunk — either exchange pairs or general extraction
        if extract_mode == "general":
            from .general_extractor import extract_memories

            chunks = extract_memories(content)
            # Each chunk already has memory_type; use it as the room name
        else:
            chunks = chunk_exchanges(content)

        if not chunks:
            if not dry_run:
                _register_file(collection, source_file, wing, agent, signature)
            continue

        # Detect room from content (general mode uses memory_type instead)
        if extract_mode != "general":
            room = detect_convo_room(content)
        else:
            room = None  # set per-chunk below

        if dry_run:
            if extract_mode == "general":
                from collections import Counter

                type_counts = Counter(c.get("memory_type", "general") for c in chunks)
                types_str = ", ".join(f"{t}:{n}" for t, n in type_counts.most_common())
                print(f"    [DRY RUN] {filepath.name} → {len(chunks)} memories ({types_str})")
            else:
                print(f"    [DRY RUN] {filepath.name} → room:{room} ({len(chunks)} drawers)")
            total_drawers += len(chunks)
            # Track room counts
            if extract_mode == "general":
                for c in chunks:
                    room_counts[c.get("memory_type", "general")] += 1
            else:
                room_counts[room] += 1
            continue

        if extract_mode != "general":
            room_counts[room] += 1

        # Serialize this source and append the new revision without deleting history.
        drawers_added, room_delta, skipped = _file_chunks_locked(
            collection,
            source_file,
            chunks,
            wing,
            room,
            agent,
            extract_mode,
            signature=signature,
            revision=source_revision(content, extract_mode),
        )
        if skipped:
            files_skipped += 1
            continue
        for r, n in room_delta.items():
            room_counts[r] += n

        total_drawers += drawers_added
        print(f"  + [{i:4}/{len(files)}] {filepath.name[:50]:50} +{drawers_added}")

    print(f"\n{'=' * 55}")
    print("  Done.")
    print(f"  Files processed: {len(files) - files_skipped}")
    print(f"  Files skipped (already filed): {files_skipped}")
    print(f"  Drawers filed: {total_drawers}")
    if room_counts:
        print("\n  By room:")
        for room, count in sorted(room_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"    {room:20} {count} files")
    print('\n  Next: castle search "what you\'re looking for"')
    print(f"{'=' * 55}\n")

    # ── Phase 2: KG enrichment (lazy import, never re-raises) ────────
    try:
        from . import kg_enricher
        from .config import CognitiveCastleConfig

        _cfg = CognitiveCastleConfig()
        _result = kg_enricher.enrich_palace(palace_path, _cfg)
        print(
            f"KG enrichment: scanned {_result['drawers_scanned']} drawers, "
            f"promoted {_result['entities_promoted']}, "
            f"wrote {_result['triples_written']} triples "
            f"in {_result['elapsed_s']}s"
        )
    except Exception as _kg_err:
        print(
            f"KG enrichment FAILED ({type(_kg_err).__name__}: {_kg_err}) — "
            f"palace unaffected; rerun mine to retry"
        )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python convo_miner.py <convo_dir> [--palace PATH] [--limit N] [--dry-run]")
        sys.exit(1)
    from .config import CognitiveCastleConfig

    mine_convos(sys.argv[1], palace_path=CognitiveCastleConfig().palace_path)
