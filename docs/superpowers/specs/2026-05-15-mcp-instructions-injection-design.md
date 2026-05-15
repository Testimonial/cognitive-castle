# Castle MCP `instructions` Injection — Design Spec

**Status:** Approved (brainstorm complete, 2026-05-15)
**Type:** Additive — single new MCP field, plus refined PALACE_PROTOCOL text
**Scope:** `cognitive_castle/mcp_server.py` only

---

## 1. Goal

Castle MCP server injects a behavioral protocol into the system prompt of every Claude Code session at startup, so AIs treat Castle as memory by default — without requiring per-user setup or per-AI training.

### Mechanism

The MCP protocol's `initialize` response carries an `instructions: str` field (per [MCP spec](https://modelcontextprotocol.io/specification/2024-11-05/server/lifecycle)). MCP-compliant clients inject this field into the model's system prompt at session start. Castle's MCP server currently does NOT set this field — its current `initialize` response at `mcp_server.py:1656-1666` returns only `protocolVersion`, `capabilities`, and `serverInfo`. This PR adds the `instructions` field.

### The guarantee chain

| Layer | Guarantee strength | Status before this PR |
|---|---|---|
| MCP `instructions` field | **Highest** — system-prompt injection at every session | **Missing** |
| Stop / PreCompact hooks | High — write-side via plugin install | Active |
| Plugin `SKILL.md` | Medium — fires only when AI invokes by name | Active but underused |
| CLAUDE.md | Low — only for users working IN the Castle repo | Active for Castle devs |
| Auto-memory `MEMORY.md` | Low — per-user, manual setup | Active for individual users |

The `instructions` field is the foundational layer. Anything below it is conditional.

### Success criteria

A fresh Claude Code session with Castle MCP installed shows the Castle protocol in `claude --debug` output (or equivalent system-prompt inspection) at startup. AIs in subsequent sessions:
- Search the palace before answering about past decisions
- File decision drawers during brainstorming
- Read AAAK-compressed drawers correctly (no extra tool call to fetch the spec)

---

## 2. Implementation surface

### Files modified

Only `cognitive_castle/mcp_server.py`.

### Change 1 — Replace `PALACE_PROTOCOL` text

Currently at `mcp_server.py:283`. The new text is shared by `castle_status` (existing caller) and the new `initialize` handler.

```python
PALACE_PROTOCOL = """Castle is a local verbatim memory palace storing this user's past
conversations, decisions, and entity facts. The palace is on the
user's machine — no data leaves it.

Behavioral protocol:
- Before answering about a person, project, design decision, or past
  event: call castle_search or castle_kg_query FIRST. Never guess.
- When making non-obvious design decisions during brainstorming, file
  rationale via castle_add_drawer in wing_<project> / decisions.
- If a fact has changed (renamed function, moved file, person's role):
  call castle_kg_invalidate on the old, castle_kg_add for the new.

The Stop hook auto-mines completed sessions into the palace. Trust the
palace over recollection — it stores exact words."""
```

The current PALACE_PROTOCOL text (5 numbered rules including "ON WAKE-UP: Call castle_status...") is replaced wholesale. The "ON WAKE-UP" rule is dropped because it's circular when this text is itself injected at startup.

### Change 2 — Add two module-level helpers

Place after the AAAK_SPEC definition (around line 300):

```python
def _palace_state_line() -> str | None:
    """One-line palace summary, or None if palace is unavailable.

    Best-effort: any exception (no palace, lock contention, lance error)
    returns None so initialize never fails because of a state read.
    """
    try:
        if not os.path.isdir(_config.palace_path):
            return "Palace state: not initialized. Run `castle init <dir>` to set up."
        col = _get_collection(create=False)
        if not col:
            return "Palace state: empty (no drawers filed yet)."
        count = col.count()
        wings = {(m or {}).get("wing", "unknown") for m in _get_cached_metadata(col)}
        return f"Palace state: {count} drawers across {len(wings)} wings."
    except Exception:
        logger.exception("_palace_state_line failed")
        return None


def _build_instructions() -> str:
    """Compose the system-prompt injection: protocol + AAAK + palace state."""
    parts = [PALACE_PROTOCOL, "", AAAK_SPEC]
    state = _palace_state_line()
    if state:
        parts.extend(["", state])
    return "\n".join(parts)
```

### Change 3 — Add `instructions` to the `initialize` response

In the `handle_request` function around `mcp_server.py:1656-1666`:

```python
# BEFORE:
"result": {
    "protocolVersion": negotiated,
    "capabilities": {"tools": {}},
    "serverInfo": {"name": "cognitive-castle", "version": __version__},
},

# AFTER:
"result": {
    "protocolVersion": negotiated,
    "capabilities": {"tools": {}},
    "serverInfo": {"name": "cognitive-castle", "version": __version__},
    "instructions": _build_instructions(),
},
```

### Composition shape

Approximate byte counts of the injected text:
- `PALACE_PROTOCOL` (refined): ~600 chars
- `AAAK_SPEC` (existing, unchanged): ~600 chars
- Palace state line: ~70 chars
- **Total injection per session: ~1300 chars**

### Error budget

Initialize must never fail because of a palace read. `_palace_state_line` swallows all exceptions and returns None. `_build_instructions` then omits the dynamic line. The protocol + AAAK still inject.

---

## 3. Testing strategy

### Scope

Three unit tests covering the new behavior. Tests assert substrings rather than exact wording so the protocol text can evolve without test churn.

### Test surface changes

| File | Delete | Update | Add |
|---|--:|--:|--:|
| `tests/test_mcp_server.py` | 0 | 0 | 4 |
| **Totals** | 0 | 0 | 4 |

### New tests (4 total)

**1. `initialize` response includes `instructions` field**

```python
def test_initialize_response_includes_instructions():
    from cognitive_castle.mcp_server import handle_request
    response = handle_request({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05"},
    })
    assert "instructions" in response["result"]
    assert isinstance(response["result"]["instructions"], str)
    assert len(response["result"]["instructions"]) > 100
```

**2. Injected instructions contain protocol + AAAK substrings**

```python
def test_initialize_instructions_contains_protocol_and_aaak():
    from cognitive_castle.mcp_server import handle_request
    response = handle_request({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05"},
    })
    text = response["result"]["instructions"]
    # Behavioral protocol markers
    assert "castle_search" in text
    assert "castle_add_drawer" in text
    assert "Never guess" in text
    # AAAK marker
    assert "AAAK" in text
    assert "ENTITIES:" in text
```

**3. Palace-state line graceful-fallback on read failure**

```python
def test_palace_state_line_returns_none_on_failure(monkeypatch):
    """Initialize must never fail because of a palace state read.
    A broken palace path or LanceDB error returns None; injection
    proceeds without the dynamic line."""
    from cognitive_castle import mcp_server

    def _raise(*args, **kwargs):
        raise RuntimeError("lance broken")

    monkeypatch.setattr(mcp_server, "_get_collection", _raise)
    # Ensure the palace dir check passes so we reach _get_collection
    monkeypatch.setattr(mcp_server.os.path, "isdir", lambda p: True)
    assert mcp_server._palace_state_line() is None
```

**4. PALACE_PROTOCOL no longer has the circular "ON WAKE-UP" rule**

```python
def test_palace_protocol_has_no_circular_wakeup_rule():
    """PALACE_PROTOCOL is now injected at session start; it shouldn't
    instruct the AI to call castle_status (the protocol's source) on
    wake-up — that's the very thing the injection replaces."""
    from cognitive_castle.mcp_server import PALACE_PROTOCOL
    assert "ON WAKE-UP" not in PALACE_PROTOCOL
    assert "Call castle_status" not in PALACE_PROTOCOL
```

### Integration check (manual, not automated)

Restart the running Castle MCP server and start a fresh Claude Code session. Confirm via `claude --debug` (or equivalent system-prompt inspection) that the system prompt contains a section like:

```
## castle
Castle is a local verbatim memory palace storing this user's past
conversations, decisions, and entity facts...
```

This validates that Claude Code's MCP client actually injects the field. If the injection doesn't show, that's a Claude Code (not Castle) issue — but the MCP spec mandates injection, so all compliant clients should do it.

### Coverage targets

- `_build_instructions`: 100% line coverage (one straight-through path + the dynamic-line conditional).
- `_palace_state_line`: 3 paths covered (no palace dir / empty palace / exception). The happy path with real data is exercised by test 2 above.
- `initialize` handler: the new field is asserted in test 1.

### Risk register

| # | Risk | Likelihood | Mitigation |
|---|---|---|---|
| 1 | `_palace_state_line` slow on large palaces (the user's main palace has ~64k drawers per today's `castle_status`) | Low | `col.count()` is O(1) in LanceDB; `_get_cached_metadata` already uses an in-process cache. If profiling shows latency > 100ms in init, drop the wing-count from the dynamic line. |
| 2 | Existing `castle_status` callers expecting "ON WAKE-UP" wording break | Very Low | The text is informational; no tool/test depends on the exact wording. Single-user system — only the user's AI agents see it. |
| 3 | MCP client doesn't honor the `instructions` field (non-compliant client) | Low | Out of Castle's control. Claude Code is the primary client and is MCP-compliant. The field is harmless if ignored. |
| 4 | Cached metadata is stale, making the wing count wrong | Low | The metadata is informational, not load-bearing. A stale count is no worse than no count. |

### Non-goals

- Re-testing MCP JSON-RPC handshake mechanics.
- Asserting the EXACT injected text byte-for-byte.
- Behavior change in `castle_status` beyond the new PALACE_PROTOCOL text.
- A SessionStart hook (deferred to follow-up if needed).
- Diary-write rule in the protocol (Stop hook handles transcript mining).

---

## 4. Acceptance criteria

- All 4 new tests pass.
- `python -m pytest tests/ --ignore=tests/benchmarks -m "not slow"` reports zero failures.
- `ruff check .` and `ruff format --check .` both clean.
- Manual integration check confirms the `instructions` field reaches Claude Code's system prompt after MCP server restart.
- PR merged via `gh pr merge --merge --delete-branch` to `develop`.

---

## 5. Rollout

Single PR on branch `feat/mcp-instructions-injection`. Conventional commit:

```
feat(mcp): inject behavioral protocol via initialize.instructions
```

No deprecation window. The behavior change is additive (new field). Existing clients that ignore `instructions` see no change. MCP-compliant clients (including Claude Code) gain automatic protocol injection at session start.

After merge: restart any long-running Castle MCP server processes to pick up the new initialize response. This is a one-time operation per user — future sessions get the injection automatically.

---

## 6. Out of scope (potential follow-ups)

**SessionStart hook for dynamic recent-context pre-fetch.** A `.claude-plugin/hooks/` entry that runs at session start and injects "you have N drawers, last mine was X, recent wings include Y, Z" as `<additional-context>`. Differs from this PR's MCP `instructions` in two ways: (a) it can be more dynamic without affecting MCP startup latency; (b) it's a Claude Code-specific feature (other MCP clients won't have it). Worth considering after this PR ships if the static dynamic line proves insufficient.

**Refining the SKILL.md to be auto-suggestable.** The plugin's `skills/castle/SKILL.md` currently fires only when explicitly invoked. With the MCP `instructions` already covering the same behavioral protocol, the skill may become redundant — or may evolve into a richer per-task playbook (e.g., "use this skill when starting a new feature in Castle"). Defer decision.
