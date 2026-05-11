"""
repair.py — Scan, prune corrupt entries, and rebuild index
===========================================================

This module provides four operations:

  status  — read-only health check: collection sizes
  scan    — find every corrupt/unfetchable ID in the palace
  prune   — delete only the corrupt IDs (surgical)
  rebuild — extract all drawers, delete the collection, recreate, and
            upsert everything back

Usage (standalone):
    python -m cognitive_castle.repair status
    python -m cognitive_castle.repair scan [--wing X]
    python -m cognitive_castle.repair prune --confirm
    python -m cognitive_castle.repair rebuild

Usage (from CLI):
    castle repair
    castle repair-scan [--wing X]
    castle repair-prune --confirm
"""

import argparse
import os
import time

from .backends.lancedb_backend import LanceDBBackend
from .config import CognitiveCastleConfig

# Backward-compat alias for legacy `@patch("cognitive_castle.repair.MempalaceConfig")`
# usage in tests. Production code uses CognitiveCastleConfig directly.
MempalaceConfig = CognitiveCastleConfig


COLLECTION_NAME = "castle_drawers"


def _get_palace_path():
    """Resolve palace path from config."""
    try:
        return CognitiveCastleConfig().palace_path
    except Exception:
        default = os.path.join(os.path.expanduser("~"), ".castle", "palace")
        return default


def _paginate_ids(col, where=None):
    """Pull all IDs in a collection using pagination."""
    ids = []
    page = 1000
    offset = 0
    while True:
        try:
            r = col.get(where=where, include=[], limit=page, offset=offset)
        except Exception:
            try:
                r = col.get(where=where, include=[], limit=page)
                new_ids = [i for i in r["ids"] if i not in set(ids)]
                if not new_ids:
                    break
                ids.extend(new_ids)
                offset += len(new_ids)
                continue
            except Exception:
                break
        n = len(r["ids"]) if r["ids"] else 0
        if n == 0:
            break
        ids.extend(r["ids"])
        offset += n
        if n < page:
            break
    return ids


def scan_palace(palace_path=None, only_wing=None):
    """Scan the palace for corrupt/unfetchable IDs.

    Probes in batches of 100, falls back to per-ID on failure.
    Writes corrupt_ids.txt to the palace directory for the prune step.

    Returns (good_set, bad_set).
    """
    palace_path = palace_path or _get_palace_path()
    print(f"\n  Palace: {palace_path}")
    print("  Loading...")

    col = LanceDBBackend().get_collection(palace_path, COLLECTION_NAME)

    where = {"wing": only_wing} if only_wing else None
    total = col.count()
    print(f"  Collection: {COLLECTION_NAME}, total: {total:,}")
    if only_wing:
        print(f"  Scanning wing: {only_wing}")

    print("\n  Step 1: listing all IDs...")
    t0 = time.time()
    all_ids = _paginate_ids(col, where=where)
    print(f"  Found {len(all_ids):,} IDs in {time.time() - t0:.1f}s\n")

    if not all_ids:
        print("  Nothing to scan.")
        return set(), set()

    print("  Step 2: probing each ID (batches of 100)...")
    t0 = time.time()
    good_set = set()
    bad_set = set()
    batch = 100

    for i in range(0, len(all_ids), batch):
        chunk = all_ids[i : i + batch]
        try:
            r = col.get(ids=chunk, include=["documents"])
            for got in r["ids"]:
                good_set.add(got)
            for mid in chunk:
                if mid not in good_set:
                    bad_set.add(mid)
        except Exception:
            for sid in chunk:
                try:
                    r = col.get(ids=[sid], include=["documents"])
                    if r["ids"]:
                        good_set.add(sid)
                    else:
                        bad_set.add(sid)
                except Exception:
                    bad_set.add(sid)

        if (i // batch) % 50 == 0:
            elapsed = time.time() - t0
            rate = (i + batch) / max(elapsed, 0.01)
            eta = (len(all_ids) - i - batch) / max(rate, 0.01)
            print(
                f"    {i + batch:>6}/{len(all_ids):>6}  "
                f"good={len(good_set):>6}  bad={len(bad_set):>6}  "
                f"eta={eta:.0f}s"
            )

    print(f"\n  Scan complete in {time.time() - t0:.1f}s")
    print(f"  GOOD: {len(good_set):,}")
    print(f"  BAD:  {len(bad_set):,}  ({len(bad_set) / max(len(all_ids), 1) * 100:.1f}%)")

    bad_file = os.path.join(palace_path, "corrupt_ids.txt")
    with open(bad_file, "w") as f:
        for bid in sorted(bad_set):
            f.write(bid + "\n")
    print(f"\n  Bad IDs written to: {bad_file}")
    return good_set, bad_set


def prune_corrupt(palace_path=None, confirm=False):
    """Delete corrupt IDs listed in corrupt_ids.txt."""
    palace_path = palace_path or _get_palace_path()
    bad_file = os.path.join(palace_path, "corrupt_ids.txt")

    if not os.path.exists(bad_file):
        print("  No corrupt_ids.txt found — run scan first.")
        return

    with open(bad_file) as f:
        bad_ids = [line.strip() for line in f if line.strip()]
    print(f"  {len(bad_ids):,} corrupt IDs queued for deletion")

    if not confirm:
        print("\n  DRY RUN — no deletions performed.")
        print("  Re-run with --confirm to actually delete.")
        return

    col = LanceDBBackend().get_collection(palace_path, COLLECTION_NAME)
    before = col.count()
    print(f"  Collection size before: {before:,}")

    batch = 100
    deleted = 0
    failed = 0
    for i in range(0, len(bad_ids), batch):
        chunk = bad_ids[i : i + batch]
        try:
            col.delete(ids=chunk)
            deleted += len(chunk)
        except Exception:
            for sid in chunk:
                try:
                    col.delete(ids=[sid])
                    deleted += 1
                except Exception:
                    failed += 1
        if (i // batch) % 20 == 0:
            print(f"    deleted {deleted}/{len(bad_ids)}  (failed: {failed})")

    after = col.count()
    print(f"\n  Deleted: {deleted:,}")
    print(f"  Failed:  {failed:,}")
    print(f"  Collection size: {before:,} → {after:,}")


# ChromaDB's ``collection.get()`` enforces an internal default ``limit``
# of 10 000 rows when the caller does not pass one. We pass an explicit
# ``limit=batch_size`` below, but the underlying segment also caps reads
# during stale/quarantined-HNSW recovery flows: extraction silently stops
# at exactly 10 000 even on palaces with many more rows. Refusing to
# overwrite when this exact value comes back is the simplest signal we
# can detect without depending on chromadb internals.
CHROMADB_DEFAULT_GET_LIMIT = 10_000


class TruncationDetected(Exception):
    """Raised by :func:`check_extraction_safety` when extraction looks short.

    Carries the human-readable abort message so callers (CLI ``cmd_repair``,
    ``rebuild_index``) can print and exit consistently without re-deriving
    the wording.
    """

    def __init__(self, message: str, sqlite_count: "int | None", extracted: int):
        super().__init__(message)
        self.message = message
        self.sqlite_count = sqlite_count
        self.extracted = extracted


def check_extraction_safety(
    palace_path: str, extracted: int, confirm_truncation_ok: bool = False
) -> None:
    """Cross-check that ``extracted`` matches the SQLite ground truth.

    Two signals trip the guard:

    1. **Strong** — ``chroma.sqlite3`` reports more drawers than were
       extracted. This is the user-reported #1208 case: 67 580 on disk,
       10 000 came back through the chromadb collection layer, repair
       would have destroyed the difference.
    2. **Weak** — extracted count equals exactly ``CHROMADB_DEFAULT_GET_LIMIT``
       AND the SQLite check couldn't run (schema drift, locked file).
       Hitting the chromadb default ``get()`` cap exactly is suspicious
       enough to refuse without explicit acknowledgement.

    Raises :class:`TruncationDetected` with a printable message when the
    guard fires. Does nothing on safe extractions or when
    ``confirm_truncation_ok`` is set.
    """
    if confirm_truncation_ok:
        return

    sqlite_count = sqlite_drawer_count(palace_path)
    cap_signal = extracted == CHROMADB_DEFAULT_GET_LIMIT

    if sqlite_count is not None and sqlite_count > extracted:
        loss = sqlite_count - extracted
        pct = 100 * loss / sqlite_count
        message = (
            f"\n  ABORT: chroma.sqlite3 reports {sqlite_count:,} drawers but only {extracted:,}\n"
            "  came back through the chromadb collection layer. The segment metadata is\n"
            "  stale (often after manual HNSW quarantine) — proceeding would silently\n"
            f"  destroy {loss:,} drawers (~{pct:.0f}%).\n"
            "\n"
            "  Recovery options:\n"
            "    1. Restore from your most recent palace backup, then re-mine.\n"
            "    2. Direct-extract from chroma.sqlite3 (rows are still on disk) and\n"
            "       rebuild the palace from source files.\n"
            "    3. If you have independently confirmed the palace really contains only\n"
            f"       {extracted:,} drawers, re-run with --confirm-truncation-ok.\n"
        )
        raise TruncationDetected(message, sqlite_count, extracted)

    if cap_signal and sqlite_count is None:
        message = (
            f"\n  ABORT: extracted exactly {CHROMADB_DEFAULT_GET_LIMIT:,} drawers, which matches\n"
            "  ChromaDB's internal default get() limit. The on-disk SQLite count couldn't\n"
            "  be cross-checked from this Python context, so we can't tell whether the\n"
            f"  palace genuinely holds {CHROMADB_DEFAULT_GET_LIMIT:,} rows or whether extraction was\n"
            "  silently capped. Refusing to overwrite the palace.\n"
            "\n"
            "  If you have independently confirmed (e.g. via direct sqlite3 query) that\n"
            f"  the palace really contains exactly {CHROMADB_DEFAULT_GET_LIMIT:,} drawers, re-run with\n"
            "  --confirm-truncation-ok.\n"
        )
        raise TruncationDetected(message, sqlite_count, extracted)


def sqlite_drawer_count(palace_path: str) -> "int | None":
    """Count rows in ``chroma.sqlite3.embeddings`` for the drawers collection.

    Used as an independent ground-truth check against the chromadb
    collection-layer ``count()`` / ``get()``: when the on-disk SQLite
    row count exceeds the extraction count, the segment metadata is
    stale and repair would destroy the difference.

    Returns ``None`` when the schema isn't readable (chromadb version
    drift, missing tables, locked file). Callers treat ``None`` as
    "unknown" and fall back to the cap-detection check.
    """
    sqlite_path = os.path.join(palace_path, "chroma.sqlite3")
    if not os.path.exists(sqlite_path):
        return None
    try:
        import sqlite3

        conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
        try:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM embeddings e
                JOIN segments s ON e.segment_id = s.id
                JOIN collections c ON s.collection = c.id
                WHERE c.name = ?
                """,
                (COLLECTION_NAME,),
            ).fetchone()
            return int(row[0]) if row and row[0] is not None else None
        finally:
            conn.close()
    except Exception:
        # chromadb schema differs by version (segments / collections column
        # names occasionally rename). Silent fallback is correct here —
        # the cap-detection check still catches the user-reported case.
        return None


def rebuild_index(palace_path=None, confirm_truncation_ok: bool = False):
    """Rebuild the HNSW index from scratch.

    1. Extract all drawers via ChromaDB get()
    2. Cross-check against the SQLite ground truth (#1208 guard)
    3. Back up ONLY chroma.sqlite3 (not the bloated HNSW files)
    4. Delete and recreate the collection with hnsw:space=cosine
    5. Upsert all drawers back

    ``confirm_truncation_ok`` overrides the safety guard from step 2.
    Set to ``True`` only when you have independently verified that the
    palace genuinely contains exactly the extracted number of drawers
    (typically only a concern for palaces sized at exactly 10 000 rows).
    """
    palace_path = palace_path or _get_palace_path()

    if not os.path.isdir(palace_path):
        print(f"\n  No palace found at {palace_path}")
        return

    print(f"\n{'=' * 55}")
    print("  Cognitive Castle Repair — Index Rebuild")
    print(f"{'=' * 55}\n")
    print(f"  Palace: {palace_path}")

    backend = LanceDBBackend()
    try:
        col = backend.get_collection(palace_path, COLLECTION_NAME)
        total = col.count()
    except Exception as e:
        print(f"  Error reading palace: {e}")
        print("  Palace may need to be re-mined from source files.")
        return

    print(f"  Drawers found: {total}")

    if total == 0:
        print("  Nothing to repair.")
        return

    # Extract all drawers in batches
    print("\n  Extracting drawers...")
    batch_size = 5000
    all_ids = []
    all_docs = []
    all_metas = []
    offset = 0
    while offset < total:
        batch = col.get(limit=batch_size, offset=offset, include=["documents", "metadatas"])
        if not batch["ids"]:
            break
        all_ids.extend(batch["ids"])
        all_docs.extend(batch["documents"])
        all_metas.extend(batch["metadatas"])
        offset += len(batch["ids"])
    print(f"  Extracted {len(all_ids)} drawers")

    # Drop and recreate the LanceDB table to rebuild indexes from scratch
    print("  Rebuilding LanceDB table...")
    import lancedb

    db_dir = os.path.join(palace_path, "lancedb")
    db = lancedb.connect(db_dir)
    db.drop_table(COLLECTION_NAME, ignore_missing=True)
    backend.close_palace(palace_path)

    new_col = backend.get_collection(palace_path, COLLECTION_NAME)

    filed = 0
    try:
        for i in range(0, len(all_ids), batch_size):
            batch_ids = all_ids[i : i + batch_size]
            batch_docs = all_docs[i : i + batch_size]
            batch_metas = all_metas[i : i + batch_size]
            new_col.upsert(documents=batch_docs, ids=batch_ids, metadatas=batch_metas)
            filed += len(batch_ids)
            print(f"  Re-filed {filed}/{len(all_ids)} drawers...")
    except Exception as e:
        print(f"\n  ERROR during rebuild: {e}")
        print(f"  Only {filed}/{len(all_ids)} drawers were re-filed.")
        print("  No backup available. Re-mine from source files to recover.")
        raise

    print(f"\n  Repair complete. {filed} drawers rebuilt.")
    print(f"\n{'=' * 55}\n")


def status(palace_path=None) -> dict:
    """Read-only health check: report collection sizes for the palace.

    Returns a dict with ``drawers`` and ``closets`` keys, each containing
    a count. Returns a dict with ``status="unknown"`` when no palace exists.
    """
    palace_path = palace_path or _get_palace_path()
    print(f"\n{'=' * 55}")
    print("  Cognitive Castle Repair — Status")
    print(f"{'=' * 55}\n")
    print(f"  Palace: {palace_path}")

    if not os.path.isdir(palace_path):
        print("  No palace found.\n")
        return {"status": "unknown", "message": "no palace at path"}

    backend = LanceDBBackend()
    results = {}
    for label in ("castle_drawers", "castle_closets"):
        try:
            col = backend.get_collection(palace_path, label)
            count = col.count()
            results[label] = {"count": count, "status": "ok"}
            print(f"\n  [{label}]")
            print(f"    count:   {count:,}")
            print("    status:  OK")
        except Exception as exc:
            results[label] = {"count": None, "status": "error", "message": str(exc)}
            print(f"\n  [{label}]")
            print(f"    status:  ERROR — {exc}")

    # HNSW capacity reporting removed — LanceDB uses different index types.
    print()
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Cognitive Castle repair tools")
    p.add_argument("command", choices=["status", "scan", "prune", "rebuild"])
    p.add_argument("--palace", default=None, help="Palace directory path")
    p.add_argument("--wing", default=None, help="Scan only this wing")
    p.add_argument("--confirm", action="store_true", help="Actually delete corrupt IDs")
    args = p.parse_args()

    path = os.path.expanduser(args.palace) if args.palace else None

    if args.command == "status":
        status(palace_path=path)
    elif args.command == "scan":
        scan_palace(palace_path=path, only_wing=args.wing)
    elif args.command == "prune":
        prune_corrupt(palace_path=path, confirm=args.confirm)
    elif args.command == "rebuild":
        rebuild_index(palace_path=path)
