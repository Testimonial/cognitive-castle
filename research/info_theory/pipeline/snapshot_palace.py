"""Snapshot the live LanceDB palace so the experiment reads from a
frozen state. Critical for reproducibility — the palace grows
continuously via the Stop hook."""

from __future__ import annotations
import hashlib
import json
import shutil
from pathlib import Path
from typing import Iterable


def snapshot_palace(src: Path, dst: Path) -> Path:
    """Copy the LanceDB directory tree at `src` into `dst`.

    Refuses to overwrite an existing snapshot — the experiment must
    explicitly delete a prior snapshot before re-running.
    """
    src = Path(src)
    dst = Path(dst)
    if dst.exists():
        raise FileExistsError(f"Snapshot target {dst} already exists; refusing to overwrite")
    shutil.copytree(src, dst)
    return dst


def compute_fingerprint(rows: Iterable[dict]) -> str:
    """Stable hash of sorted [(drawer_id, filed_at, chunk_index)] tuples.

    Tuples preserve per-drawer positional binding. Concatenating value
    lists would lose that binding — same values in different orders
    would collide.
    """
    sortable = [(r["drawer_id"], r["filed_at"], int(r["chunk_index"])) for r in rows]
    sortable.sort(key=lambda t: t[0])
    payload = json.dumps(sortable, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()
