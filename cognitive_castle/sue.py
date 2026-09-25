"""Source-scoped SUE reviews stored beside, never over, palace memories.

The public API only snapshots selected drawers and starts an isolated worker.
No model, database scan, or SUE engine import occurs at MCP initialization.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

from ._vendor.sue.sue_lenses import LENSES

MAX_SOURCE_BYTES = 100_000
PROVIDERS = ("ollama", "codex")
DEFAULT_MODELS = {"ollama": "qwen3.5:latest", "codex": "gpt-5.6-luna"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    """Atomically replace job state; readers never see partial JSON."""
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def review_dir(palace_path, run_id):
    if not isinstance(run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ValueError("Invalid SUE run ID")
    return Path(palace_path).expanduser().resolve() / ".sue" / "runs" / run_id


def _bounded_int(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer between {low} and {high}")


def _validate(drawer_ids, decision, provider, model, lens, max_turns, timeout):
    if (
        not isinstance(drawer_ids, list)
        or not 1 <= len(drawer_ids) <= 20
        or any(not isinstance(d, str) or not d or len(d) > 512 for d in drawer_ids)
        or len(set(drawer_ids)) != len(drawer_ids)
    ):
        raise ValueError(
            "Select 1–20 distinct drawer IDs containing requirements and their context"
        )
    if not isinstance(decision, str) or not decision.strip() or len(decision) > 4000:
        raise ValueError(
            "decision must state the requirement or interpretation to examine (1–4000 chars)"
        )
    if provider not in PROVIDERS:
        raise ValueError("provider must be ollama (local) or explicitly selected codex (external)")
    if model is not None and (not isinstance(model, str) or not model.strip() or len(model) > 200):
        raise ValueError("model must be a nonempty model name")
    if not isinstance(lens, str) or lens not in LENSES:
        raise ValueError(f"Unknown lens; choose from {', '.join(LENSES)}")
    _bounded_int(max_turns, "max_turns", 1, 14)
    _bounded_int(timeout, "timeout", 1, 300)


def _snapshot(collection, drawer_ids):
    result = collection.get(ids=drawer_ids, include=["documents", "metadatas"])
    records = dict(zip(result.ids, zip(result.documents, result.metadatas)))
    missing = [d for d in drawer_ids if d not in records]
    if missing:
        raise ValueError(f"Unknown drawer IDs: {', '.join(missing)}")
    sources, bundle = [], bytearray()
    for index, drawer_id in enumerate(drawer_ids, 1):
        content, metadata = records[drawer_id]
        if not isinstance(content, str) or not content.strip():
            raise ValueError(f"Drawer {drawer_id} has no text to examine")
        raw = content.encode("utf-8")
        # Metadata retains dates/revisions/supersession and separates source boundaries.
        # It is context, not an assertion that these records are current requirements.
        header = f"--- Castle source {index}: {drawer_id}; context {json.dumps(metadata, ensure_ascii=False)} ---\n"
        bundle.extend(header.encode("utf-8"))
        start = len(bundle)
        first_line = len(bundle.decode("utf-8").splitlines()) + 1
        bundle.extend(raw)
        sources.append(
            {
                "drawer_id": drawer_id,
                "snapshot": f"source-{index:03d}.txt",
                "sha256": digest(raw),
                "metadata": metadata,
                "byte_start": start,
                "byte_end": len(bundle),
                "line_start": first_line,
                "line_end": first_line + len(content.splitlines()) - 1,
            }
        )
        bundle.extend(b"\n\n")
        if len(bundle) > MAX_SOURCE_BYTES:
            raise ValueError(
                f"Selected specification exceeds {MAX_SOURCE_BYTES} UTF-8 bytes; narrow its scope"
            )
    return bytes(bundle), sources


def start_review(
    palace_path,
    drawer_ids,
    decision,
    *,
    collection_name="castle_drawers",
    collection=None,
    provider="ollama",
    model=None,
    lens="euthyphro",
    max_turns=7,
    timeout=120,
    wait=False,
):
    """Explicit selection authorizes only this bundle; never infer an external provider.

    Findings are derived artifacts under .sue/runs, accessible through review_status.
    A new invocation always creates a new run; no source drawer is modified.
    """
    _validate(drawer_ids, decision, provider, model, lens, max_turns, timeout)
    if collection is None:
        from .palace import get_collection

        collection = get_collection(palace_path, collection_name=collection_name, create=False)
    bundle, sources = _snapshot(collection, drawer_ids)
    run_id = uuid.uuid4().hex
    directory = review_dir(palace_path, run_id)
    directory.mkdir(parents=True, mode=0o700)
    directory.chmod(0o700)
    for source in sources:
        with (directory / source["snapshot"]).open("xb") as f:
            f.write(bundle[source["byte_start"] : source["byte_end"]])
    (directory / "specification.txt").write_bytes(bundle)
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at": time.time(),
        "kind": "derived_requirement_review",
        "decision": decision,
        "collection_name": collection_name,
        "sources": sources,
        "spec_sha256": digest(bundle),
        "provider": provider,
        "model": model or DEFAULT_MODELS[provider],
        "lens": lens,
        "max_turns": max_turns,
        "timeout": timeout,
        "max_provider_attempts": max_turns * 2,
        "external_processing": provider == "codex",
        "engine": json.loads((Path(__file__).parent / "_vendor/sue/UPSTREAM.json").read_text()),
    }
    write_json(directory / "manifest.json", manifest)
    write_json(directory / "state.json", {"status": "queued", "updated_at": time.time()})
    command = [sys.executable, "-m", "cognitive_castle.sue_worker", str(directory)]
    # No content in argv. A separate process keeps MCP responsive and isolates SUE's transport.
    try:
        with (directory / "worker.log").open("xb") as log:
            child = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
                cwd=directory,
                close_fds=True,
            )
            if wait:
                child.wait()
    except OSError as exc:
        write_json(
            directory / "state.json",
            {
                "status": "failed",
                "updated_at": time.time(),
                "error": f"Cannot start SUE worker: {exc}",
            },
        )
    return review_status(palace_path, run_id)


def _state(directory, manifest):
    state = json.loads((directory / "state.json").read_text(encoding="utf-8"))
    if state["status"] not in ("queued", "running"):
        return state
    expired = (
        time.time()
        > manifest["created_at"]
        + manifest["max_provider_attempts"] * (manifest["timeout"] + 15)
        + 90
    )
    if state["status"] == "running" and os.name == "posix":
        try:
            os.kill(state["pid"], 0)
        except ProcessLookupError:
            expired = True
    if state["status"] == "queued" and time.time() - state["updated_at"] > 90:
        expired = True
    return (
        {
            **state,
            "status": "interrupted",
            "error": "Worker exited or exceeded its run deadline; inspect worker.log",
        }
        if expired
        else state
    )


def review_status(palace_path, run_id=None):
    """List recent reviews, or retrieve a run with its full trace and source links."""
    if run_id is None:
        root = Path(palace_path).expanduser().resolve() / ".sue/runs"
        directories = sorted(
            root.glob("*/manifest.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )[:20]
        runs = []
        for file in directories:
            manifest = json.loads(file.read_text(encoding="utf-8"))
            runs.append(
                {
                    "run_id": manifest["run_id"],
                    "decision": manifest["decision"],
                    **_state(file.parent, manifest),
                }
            )
        return {"runs": runs, "lenses": list(LENSES), "default_provider": "ollama"}
    directory = review_dir(palace_path, run_id)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    result = {"run_id": run_id, "manifest": manifest, **_state(directory, manifest)}
    if (directory / "trace.json").exists():
        result["trace"] = json.loads((directory / "trace.json").read_text(encoding="utf-8"))
        result["report"] = (directory / "report.md").read_text(encoding="utf-8")
    result["artifacts"] = str(directory)
    return result


def configure_parser(subparsers):
    parser = subparsers.add_parser("sue", help="Examine selected Castle requirements with SUE")
    actions = parser.add_subparsers(dest="sue_action", required=True)
    review = actions.add_parser("review", help="Start a background review of selected drawers")
    review.add_argument("--drawer", dest="drawer_ids", action="append", required=True)
    review.add_argument("--decision", required=True, help="Requirement/interpretation to examine")
    review.add_argument(
        "--provider",
        choices=PROVIDERS,
        default="ollama",
        help="codex explicitly sends the selected bundle to its configured provider",
    )
    review.add_argument("--model", default=None)
    review.add_argument("--lens", choices=sorted(LENSES), default="euthyphro")
    review.add_argument("--max-turns", type=int, default=7)
    review.add_argument(
        "--timeout", type=int, default=120, help="Seconds per model attempt (max 300)"
    )
    review.add_argument("--wait", action="store_true", help="Wait for the result in the CLI")
    status = actions.add_parser("status", help="List recent runs or retrieve one complete review")
    status.add_argument("run_id", nargs="?")


def cmd_sue(args):
    from .config import CognitiveCastleConfig

    config = CognitiveCastleConfig()
    palace_path = args.palace or config.palace_path
    try:
        if args.sue_action == "status":
            result = review_status(palace_path, args.run_id)
        else:
            result = start_review(
                palace_path,
                args.drawer_ids,
                args.decision,
                collection_name=config.collection_name,
                provider=args.provider,
                model=args.model,
                lens=args.lens,
                max_turns=args.max_turns,
                timeout=args.timeout,
                wait=args.wait,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(1) from exc
    if result.get("status") in ("failed", "interrupted"):
        raise SystemExit(1)
