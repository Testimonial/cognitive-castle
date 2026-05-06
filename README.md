<div align="center">

# Cognitive Castle

**Local-first persistent memory for AI agents.** Verbatim storage, pluggable vector backend, 96.6% R@5 raw on LongMemEval — zero API calls.

[![][version-shield]][release-link]
[![][python-shield]][python-link]
[![][license-shield]][license-link]

</div>

---

## What it is

Cognitive Castle stores conversation history and project context as
verbatim text and retrieves it with semantic search. It does not
summarise, extract, or paraphrase. The index is structured — people and
projects become *wings*, topics become *rooms*, and original content
lives in *drawers* — so searches can be scoped instead of running
against a flat corpus.

The retrieval layer is pluggable. The default is **LanceDB**; the
backend interface is in
[`cognitive_castle/backends/base.py`](cognitive_castle/backends/base.py)
and alternative backends can be dropped in without touching the rest of
the system.

Nothing leaves your machine unless you opt in.

---

## Install

```bash
git clone https://github.com/Testimonial/cognitive-castle.git
cd cognitive-castle
pip install -e .
```

Verify:

```bash
castle --version
# Cognitive Castle 3.3.3
```

## Quickstart

```bash
# 1. Detect rooms from your folder structure (and mine if you pass --yes)
castle init ~/projects/myapp --yes

# 2. Mine more content into the palace later
castle mine ~/projects/myapp                      # project files
castle mine ~/.claude/projects/ --mode convos     # Claude Code sessions

# 3. Search
castle search "why did we switch to GraphQL"
castle search "auth flow" --wing myapp --room backend

# 4. Load wake-up context for a fresh AI session
castle wake-up
castle wake-up --wing myapp                       # project-scoped

# 5. Inspect the palace
castle status
```

## Connect to Claude Code (or any MCP client)

Cognitive Castle ships an MCP server with **29 tools** for palace
reads/writes, knowledge-graph queries, cross-wing navigation, drawer
management, and agent diaries.

```bash
claude mcp add castle -- castle-mcp
```

Restart your AI client and the `castle_*` tools become available
mid-conversation.

---

## CLI overview

| Command | Purpose |
|---|---|
| `castle init <dir>` | Detect rooms from folder structure; with `--yes`, also mines |
| `castle mine <dir>` | Mine project files (default mode) |
| `castle mine <dir> --mode convos` | Mine conversation exports (Claude Code, Claude.ai, ChatGPT, Slack) |
| `castle search "query"` | Semantic search; filter with `--wing`, `--room` |
| `castle wake-up` | L0 + L1 wake-up context (~600–900 tokens) |
| `castle status` | Drawer counts per wing/room |
| `castle mcp` | Print the MCP setup command |
| `castle repair --clean-locks` | Remove stale lock files (>24 h) |
| `castle repair-status` | Read-only health check |

Full help: `castle --help`, `castle <command> --help`.

---

## Benchmarks

Numbers are reproducible from this repository with the commands in
[`benchmarks/BENCHMARKS.md`](benchmarks/BENCHMARKS.md). Per-question
result files are committed under `benchmarks/results_*`.

**LongMemEval — retrieval recall (R@5, 500 questions):**

| Mode | R@5 | LLM required |
|---|---|---|
| Raw (semantic search, no heuristics, no LLM) | **96.6%** | None |
| Hybrid v4, held-out 450q (tuned on 50 dev) | **98.4%** | None |
| Hybrid v4 + LLM rerank (full 500) | ≥99% | Any capable model |

The raw 96.6% requires no API key, no cloud, and no LLM at any stage.
The hybrid pipeline adds keyword boosting, temporal-proximity boosting,
and preference-pattern extraction; the held-out 98.4% is the honest
generalisable figure.

The rerank pipeline promotes the best candidate out of the top-20
retrieved sessions using an LLM reader. It works with any reasonably
capable model. We do not headline a "100%" number because the last 0.6%
was reached by inspecting specific wrong answers, which
`benchmarks/BENCHMARKS.md` flags as teaching to the test.

**Other benchmarks (full results in [`benchmarks/BENCHMARKS.md`](benchmarks/BENCHMARKS.md)):**

| Benchmark | Metric | Score | Notes |
|---|---|---|---|
| LoCoMo (session, top-10, no rerank) | R@10 | 60.3% | 1,986 questions |
| LoCoMo (hybrid v5, top-10, no rerank) | R@10 | 88.9% | Same set |
| ConvoMem (all categories, 250 items) | Avg recall | 92.9% | 50 per category |
| MemBench (ACL 2025, 8,500 items) | R@5 | 80.3% | All categories |

**Reproducing every result:**

```bash
git clone https://github.com/Testimonial/cognitive-castle.git
cd cognitive-castle
pip install -e ".[dev]"
# see benchmarks/README.md for dataset download commands
python benchmarks/longmemeval_bench.py /path/to/longmemeval_s_cleaned.json
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  CLI  /  MCP server  (castle, castle-mcp — 29 tools)        │
├─────────────────────────────────────────────────────────────┤
│  Miner   Searcher   Knowledge Graph   Diary   Hooks         │
├─────────────────────────────────────────────────────────────┤
│  Backend interface  (cognitive_castle/backends/base.py)     │
├─────────────────────────────────────────────────────────────┤
│  LanceDB (default)  │  ChromaDB (legacy)  │  Your backend   │
└─────────────────────────────────────────────────────────────┘
```

- **Wings** — top-level groupings (projects, agents, conversations)
- **Rooms** — topical or structural subdivisions auto-detected from folder layout
- **Drawers** — verbatim content chunks; each one is searchable independently
- **Tunnels** — typed cross-references between drawers (graph edges)
- **Diaries** — per-agent append-only logs

## Knowledge graph

A temporal entity-relationship graph with validity windows: add, query,
invalidate, timeline. Backed by local SQLite — no extra service to run.

## Auto-save hooks

Two Claude Code hooks save context periodically and before compaction;
`castle sweep <transcript-dir>` provides per-message recall on top of the
file-level chunks the hooks produce — idempotent and resume-safe.

---

## Requirements

- Python 3.9+
- LanceDB (installed automatically)
- ~300 MB disk for the default embedding model (`all-MiniLM-L6-v2`)

No API key is required for the core path.

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgements

Cognitive Castle is a fork and continuation of the MemPalace project,
re-architected around LanceDB and the SOAR cognitive-architecture
heuristics. Original benchmark methodology and "wings/rooms/drawers"
naming preserved with credit to the upstream authors.

<!-- Link Definitions -->
[version-shield]: https://img.shields.io/badge/version-3.3.3-4dc9f6?style=flat-square&labelColor=0a0e14
[release-link]: https://github.com/Testimonial/cognitive-castle/releases
[python-shield]: https://img.shields.io/badge/python-3.9+-7dd8f8?style=flat-square&labelColor=0a0e14&logo=python&logoColor=7dd8f8
[python-link]: https://www.python.org/
[license-shield]: https://img.shields.io/badge/license-MIT-b0e8ff?style=flat-square&labelColor=0a0e14
[license-link]: https://github.com/Testimonial/cognitive-castle/blob/main/LICENSE
