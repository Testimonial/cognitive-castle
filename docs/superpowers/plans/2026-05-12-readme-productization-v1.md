# README Productization v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `README.md` with the layered-audience rewrite from spec `266eb2b9` — hero with inline SVG castle blueprint + 30-second pitch + 4-chip differentiator strip, two Mermaid auto-rendered diagrams (data flow + layered stack), new comparison section vs mem0/letta/zep, fixes for stale content from since-shipped PRs.

**Architecture:** Single-file documentation change. README rewritten in one comprehensive Write per the locked spec, then verified against 12 acceptance criteria locally + visually on GitHub after pushing the branch. No production code touched.

**Tech Stack:** Markdown, inline SVG, Mermaid (GitHub auto-renders). No new build tooling or assets.

---

## File structure

Modified:
- `README.md` (208 lines → ~341 lines projected; spec line cap is 360)

Untouched (verify nothing else gets edited):
- `cognitive_castle/` (all production code)
- `tests/`
- `pyproject.toml`
- `.claude-plugin/`

Reference (read but don't modify):
- `docs/superpowers/specs/2026-05-12-readme-productization-v1-design.md` (commit `266eb2b9`) — full source of truth

---

## Task 1: Create branch and rewrite README per spec

**Files:**
- Create: branch `feat/readme-productization-v1` from `develop`
- Modify: `README.md` (full rewrite)

- [ ] **Step 1: Read the spec end-to-end**

```bash
cat docs/superpowers/specs/2026-05-12-readme-productization-v1-design.md | head -300
```

Reading order: skim the goals/non-goals/source-of-truth sections first, then the 14-section structure starting at "File-by-file change list", then the hero SVG source block, then the Mermaid source blocks, then the acceptance criteria.

- [ ] **Step 2: Create the feature branch**

```bash
git checkout develop
git pull origin develop
git checkout -b feat/readme-productization-v1
```

Verify branch state:

```bash
git status
git log --oneline -3
```

Expected: clean working tree on `feat/readme-productization-v1`, recent commits include `266eb2b9` (spec refine) and `3300243c` (spec initial).

- [ ] **Step 3: Write the new README**

Use the `Write` tool (not `Edit`) — this is a near-complete rewrite. Produce `README.md` with the 14 sections from the spec, in this exact order:

1. Hero (centered div + title + inline SVG + tagline + 3 badges)
2. The 30-second pitch (3-4 sentences + 4-chip emoji strip)
3. Quickstart (4-step numbered code block)
4. How it works (Mermaid data flow + 2-3 sentence prose)
5. Connect to Claude Code (plugin path public + local + manual MCP fallback)
6. CLI overview (table with `reindex` + `sweep`, no `migrate`)
7. Benchmarks (verbatim from current README)
8. Why Castle vs mem0 / letta / zep (new table + 2 fairness sentences)
9. Architecture (Mermaid layered stack + 5-bullet glossary)
10. Knowledge graph (light polish)
11. Auto-save hooks (light polish — mention Stop + PreCompact)
12. Requirements (FIX: `paraphrase-multilingual-MiniLM-L12-v2`, ~500 MB disk)
13. License (verbatim)
14. Acknowledgements (verbatim, verify SOAR mention if trivial)

Then the existing footer link definitions block.

**Specific content guidance:**

**Hero SVG block** — copy the full `<svg>` source from the spec's "Hero SVG source" section verbatim. Wrap it inside the existing `<div align="center">` wrapper. Place it between the `# Cognitive Castle` title and the tagline. Add `width="640"` attribute alongside the existing `style="max-width:640px;height:auto;"` (belt-and-suspenders against GitHub's HTML sanitiser stripping the style).

Example structure:
```markdown
<div align="center">

# Cognitive Castle

<svg viewBox="0 0 320 200" xmlns="http://www.w3.org/2000/svg" width="640" style="max-width:640px;height:auto;" role="img" aria-label="...">
  ... full SVG body from spec ...
</svg>

**Local-first persistent memory for AI agents.** Verbatim. No API key. 96.6% R@5 on LongMemEval.

[![][version-shield]][release-link]
[![][python-shield]][python-link]
[![][license-shield]][license-link]

</div>
```

**30-second pitch** — use the spec's draft verbatim (or near-verbatim). The 4-chip strip is a single markdown line:

```markdown
📦 **Verbatim** · 🔒 **100% Local** · 🔌 **MCP-native** · 🆓 **No API key**
```

**Data flow Mermaid** — copy the spec's "Data flow Mermaid source" verbatim, wrapped in ```` ```mermaid ```` triple-backtick fence.

**Layered stack Mermaid** — copy the spec's "Layered stack Mermaid source" verbatim. If `Interfaces --> Logic` subgraph-to-subgraph edge fails to render on GitHub (verified in Task 3), the fallback is to draw explicit node-to-node edges instead:
```
CLI --> Miner
MCP --> Miner
Miner --> BIF
Searcher --> BIF
BIF --> Lance
```

**Comparison table** — use the spec's table verbatim. Letta's "Verbatim storage" cell is `⚠ tiered (verbatim core + summarised archive)` — NOT `❌ summarises`.

**Plugin install section** — show BOTH forms:
```markdown
```bash
# Most users:
/plugin marketplace add Testimonial/cognitive-castle
/plugin install castle@cognitive-castle

# Contributors with a local clone:
/plugin marketplace add /path/to/cognitive-castle
/plugin install castle@cognitive-castle

# then fully quit and reopen Claude Code
```
```

**CLI overview table** — match the spec exactly. Verify `castle reindex --help` and `castle sweep --help` to confirm flag shapes match the table; if any mismatch, fix the table to match reality (production code is canonical, not the spec).

```bash
castle reindex --help 2>&1 | head -10
castle sweep --help 2>&1 | head -10
```

- [ ] **Step 4: Local sanity check before commit**

```bash
wc -l README.md
```

Expected: 280-360 lines (spec cap is 360). If over 360, trim non-essential prose; if under 280, something was skipped — re-read the spec.

Check for stale-content fixes applied:

```bash
grep -nc "ChromaDB\|all-MiniLM-L6-v2\|castle migrate" README.md
```

Expected: `0` matches. If non-zero, fix.

Check for required new content:

```bash
grep -nc "paraphrase-multilingual-MiniLM-L12-v2\|castle reindex\|castle sweep\|tiered (verbatim" README.md
```

Expected: all four return `≥ 1`.

Check that SVG has accessibility attributes:

```bash
grep -nc 'role="img"\|aria-label' README.md
```

Expected: at least 2 matches (role + aria-label, both on the SVG).

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs: README productization v1 — hero SVG + Mermaid diagrams + comparison

Layered-audience rewrite per spec 266eb2b9:

- New hero with inline SVG castle blueprint (code/convos/papers wings,
  storied tunnels) + 30-second pitch + 4-chip differentiator strip
- Mermaid data-flow diagram under "How it works" (3-source ingest →
  Miner → Palace → 3-stage Searcher → consumers)
- Mermaid layered stack replaces ASCII architecture box (4 layers:
  Interfaces / Logic / Abstraction / Storage)
- New "Why Castle vs mem0/letta/zep" comparison section with fairness
  framing (letta is tiered, not just summarising)
- Plugin install path now leads (public + local-dev), manual MCP setup
  kept as fallback
- CLI table: dropped `migrate` (deleted PR #8), added `reindex` and
  `sweep`, updated `repair` description
- Stale-content fixes: embedder name now `paraphrase-multilingual-
  MiniLM-L12-v2`, "ChromaDB (legacy)" mention gone, disk estimate
  bumped to ~500 MB

PR #1 of 6-piece productization series; demo GIF, landing page,
comparison microsite, launch posts, and sample palace download
deferred to follow-up PRs.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Verify all 12 acceptance criteria locally

**Files:**
- Read-only verification, no edits unless an AC fails.

Walk each acceptance criterion from the spec and run a verification command. Each step records pass/fail.

- [ ] **Step 1: AC1 — README length ≤ 360 lines**

```bash
wc -l README.md
```

Expected: ≤ 360. If higher, identify the bloated section and trim.

- [ ] **Step 2: AC2 — Hero SVG renders inline; no `<script>`; has role/aria-label**

```bash
grep -c '<script' README.md
```

Expected: `0`.

```bash
grep -c 'role="img"' README.md
grep -c 'aria-label' README.md
```

Expected: each ≥ 1.

- [ ] **Step 3: AC3 — Two Mermaid code fences exist**

```bash
grep -c '^```mermaid' README.md
```

Expected: `2` (the data flow diagram and the layered stack).

- [ ] **Step 4: AC4 — Zero ChromaDB / old-embedder / castle-migrate mentions**

```bash
grep -cE "ChromaDB|all-MiniLM-L6-v2|castle migrate" README.md
```

Expected: `0`. If non-zero, inspect — only acceptable if it's a historical-context line that explicitly says "removed in PR #8".

- [ ] **Step 5: AC5 — Correct embedding model name**

```bash
grep -c "paraphrase-multilingual-MiniLM-L12-v2" README.md
```

Expected: ≥ 1.

- [ ] **Step 6: AC6 — CLI table includes reindex + sweep, not migrate**

```bash
grep -cE "^\| \`castle reindex" README.md
grep -cE "^\| \`castle sweep" README.md
grep -cE "^\| \`castle migrate" README.md
```

Expected: reindex ≥ 1, sweep ≥ 1, migrate = 0.

- [ ] **Step 7: AC7 — Connect section leads with plugin install path**

```bash
grep -n "/plugin marketplace add" README.md
```

Expected: at least two matches (public + local-dev forms).

- [ ] **Step 8: AC8 — Comparison table has the 6 required rows**

```bash
grep -cE "^\| Verbatim storage" README.md
grep -cE "^\| Local-first default" README.md
grep -cE "^\| API key required" README.md
grep -cE "^\| MCP-native" README.md
grep -cE "^\| Backend" README.md
grep -cE "^\| Published benchmarks" README.md
```

Expected: all six return `1`.

- [ ] **Step 9: AC9 — Defer to Task 3 (requires push + GitHub view)**

Mark as deferred; will run in Task 3.

- [ ] **Step 10: AC10 — 30-second pitch section + 4-chip strip exist**

```bash
grep -c "30-second\|30 second" README.md
```

(Note: this might be 0 if you used a different heading. The actual test is: does a short pitch section exist before Quickstart? Manual eyeball if grep returns 0.)

```bash
grep -c "📦 \*\*Verbatim\*\*" README.md
```

Expected: ≥ 1.

- [ ] **Step 11: AC11 — No production code modified**

```bash
git diff --name-only develop..HEAD
```

Expected: only `README.md` listed. If any file under `cognitive_castle/`, `tests/`, `pyproject.toml`, `.claude-plugin/` appears, revert those changes before continuing.

- [ ] **Step 12: AC12 — Commit count ≤ 3**

```bash
git log --oneline develop..HEAD | wc -l
```

Expected: 1-3. (Task 1 commit, optionally Task 2 fix commit, optionally Task 3 PR-prep commit.)

- [ ] **Step 13: Summarize and report**

If all ACs pass (or only AC9 is deferred), proceed to Task 3. If any AC failed, fix the underlying issue, re-run that AC's check, and document the fix in the commit message.

If a fix is needed:

```bash
git add README.md
git commit -m "docs: fix README AC<N> — <one-line description>"
```

---

## Task 3: Push branch, open PR, verify GitHub rendering

**Files:**
- No file edits unless a rendering issue is found.

- [ ] **Step 1: Push the branch**

```bash
git push -u origin feat/readme-productization-v1
```

Expected: clean push, new branch created on origin.

- [ ] **Step 2: Open PR via gh CLI**

```bash
gh pr create --base develop --title "docs: README productization v1 — hero SVG + Mermaid diagrams + comparison" --body "$(cat <<'EOF'
## Summary

PR #1 of a 6-piece productization series. Replaces `README.md` per spec [`2026-05-12-readme-productization-v1-design.md`](docs/superpowers/specs/2026-05-12-readme-productization-v1-design.md) (commit 266eb2b9).

- **Hero** — inline SVG castle blueprint (code/convos/papers wings, storied tunnels) + 30-second pitch + 4-chip differentiator strip
- **How it works** — Mermaid data flow diagram (3 sources → Miner → Palace → 3-stage Searcher → consumers)
- **Architecture** — Mermaid layered stack replaces ASCII boxes (4 layers, no more "ChromaDB legacy" mention)
- **Comparison** — new "Why Castle vs mem0 / letta / zep" section with fair framing (letta is tiered, not flat-summarising)
- **Plugin install** — leads with `/plugin marketplace add` flow (public + local-dev), manual MCP kept as fallback
- **CLI overview** — dropped `migrate` (deleted PR #8), added `reindex` and `sweep`
- **Stale content fixed** — embedder name is now `paraphrase-multilingual-MiniLM-L12-v2`, disk estimate ~500 MB

Deferred to follow-up PRs: demo GIF (#2), landing page (#3), comparison microsite (#4), launch post drafts (#5), sample palace download (#6).

## Test plan

- [x] AC1-AC8, AC10-AC12 verified locally (see Task 2 of plan)
- [ ] AC9 — view rendered README on github.com after merge, confirm hero SVG + 2 Mermaid blocks render correctly

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: AC9 — Visual verification of rendered README**

Open the PR's "Files changed" tab and click the README.md preview, or visit:

```
https://github.com/Testimonial/cognitive-castle/blob/feat/readme-productization-v1/README.md
```

Verify by eye:
1. **Hero SVG renders** — castle blueprint visible at the top, with three labeled wings (code/convos/papers), drawer grids, and two dotted tunnel arcs with text labels.
2. **First Mermaid block renders** under "How it works" — a left-to-right flow chart with 3 input boxes → Miner → Palace cylinder → Searcher → consumers.
3. **Second Mermaid block renders** under "Architecture" — a top-down stack with 4 subgraphs (Interfaces / Logic / Abstraction / Storage).
4. **Tables are not overflowing** on mobile (resize the browser to ~375px width to simulate).
5. **All anchor links work** — clicking a section heading in the rendered README scrolls to the right place.

If the hero SVG does NOT render (sanitiser stripped something), inspect the source on GitHub's view and check whether the SVG body is missing or just the styling. Common fixes:
- Replace `style="max-width:640px;height:auto;"` with `width="640" height="400"` attributes
- Remove the `style="..."` attribute on inner `<rect>` / `<text>` elements (move colors to `fill="..."` attributes — they're already that way in the spec, but double-check)

If a Mermaid block does NOT render (subgraph-to-subgraph edge issue), edit that block's source: replace `Interfaces --> Logic` with explicit node-to-node edges (e.g., `CLI --> Miner`, `MCP --> Miner`).

If any rendering fix is needed:

```bash
# Edit README.md to fix the issue
git add README.md
git commit -m "docs: fix README rendering — <one-line description of fix>"
git push
```

Re-verify on github.com.

- [ ] **Step 4: Mark AC9 verified, report status**

If all 12 ACs pass after Task 3, report:
- PR URL
- Final line count
- Confirmation of all 12 AC checks
- Any rendering surprises encountered

User will merge if happy.

---

## Self-Review

**Spec coverage:**
- AC1 (≤360 lines) → Task 2 Step 1, also Task 1 Step 4 pre-commit check ✓
- AC2 (SVG inline, no script, role+aria) → Task 2 Step 2 ✓
- AC3 (two Mermaid blocks) → Task 2 Step 3 ✓
- AC4 (no chroma/old-embedder/migrate) → Task 2 Step 4, also Task 1 Step 4 ✓
- AC5 (embedder name correct) → Task 2 Step 5, also Task 1 Step 4 ✓
- AC6 (CLI table updated) → Task 2 Step 6 ✓
- AC7 (plugin install leads) → Task 2 Step 7 ✓
- AC8 (comparison table rows) → Task 2 Step 8 ✓
- AC9 (renders on github) → Task 3 Step 3 ✓
- AC10 (30s pitch + chip strip) → Task 2 Step 10 ✓
- AC11 (no production code) → Task 2 Step 11 ✓
- AC12 (commit count) → Task 2 Step 12 ✓

All 12 ACs are mapped to verification steps.

**Placeholder scan:**
- "Light polish" appears in Task 1 Step 3 for Knowledge graph + Auto-save hooks sections. This is acceptable judgment-room for an implementer; the spec says these sections are largely keep-as-is and the prose is fine as-is. Not a placeholder.
- "Verify SOAR mention if trivial" — also explicit judgment-room delegation. Acceptable.
- "Manual eyeball if grep returns 0" for AC10 30s-pitch heading — explicit fallback, not a placeholder.

No "TBD", "TODO", or vague "implement later" patterns.

**Type consistency:**
- N/A (documentation, no types).

**Known judgment-required points clearly delegated:**
- Whether to verify `castle reindex --help` flag shape (Task 1 Step 3)
- Whether the subgraph edge renders or needs node-level fallback (Task 1 Step 3 + Task 3 Step 3)
- Whether to amend or new-commit on AC fix (clear in the relevant steps)

Plan complete and ready for execution.
