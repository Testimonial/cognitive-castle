# Mempalace Docs Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the docs cleanup per spec `614a2f21` — fix broken CI workflows + example commands + benchmark imports, update top-level repo docs/benchmarks/devcontainer/RFC/CLOSETS for current branding using context-aware hyphen/underscore replacement rules. 24 files modified, ~100-150 lines changed, no production code touched.

**Architecture:** Two-task plan. Task 1 (sonnet) applies the full file sweep using the spec's context-aware sed pattern set, handles 6 files that need surgical care (HOOKS_TUTORIAL.md, openclaw SKILL.md, .agents/plugins/marketplace.json, benchmarks/mine_bench.py, CHANGELOG.md, docs/schema.sql), and commits. Task 2 (haiku) verifies 21 ACs + pushes + opens PR.

**Tech Stack:** Bash, sed, gh. No production code or tests touched.

---

## File structure

Modified files (24 in scope):

**Critical functional fixes (6 files):**
- `.github/workflows/ci.yml` — `--cov=mempalace` → `--cov=cognitive_castle` (3x)
- `.github/workflows/version-guard.yml` — `mempalace/version.py` → `cognitive_castle/version.py` (4x; note: this IS an actual on-disk path used by `grep`, so it MUST use underscore — Python package dir name)
- `examples/basic_mining.py` — print statement `mempalace ...` → `castle ...`
- `examples/convo_import.py` — print statement `mempalace ...` → `castle ...`
- `examples/mcp_setup.md` — `mempalace-mcp` → `castle-mcp` (binary name)
- `benchmarks/mine_bench.py` — Python imports + `mempalace.yaml` fixture filename

**Surgical-care files (3 files):**
- `examples/HOOKS_TUTORIAL.md` — doubly broken (refs nonexistent shell scripts + stale commands)
- `integrations/openclaw/SKILL.md` — full plugin metadata sweep (6+ fields)
- `.agents/plugins/marketplace.json` — points to deleted `.codex-plugin/` (delete or update — investigate)

**Bulk-sed files (12 files):**
- `examples/gemini_cli_setup.md`
- `benchmarks/README.md`, `benchmarks/BENCHMARKS.md`, `benchmarks/HYBRID_MODE.md`
- `CONTRIBUTING.md`, `AGENTS.md`, `MISSION.md`, `ROADMAP.md`, `SECURITY.md`
- `.devcontainer/devcontainer.json`, `.devcontainer/post-create.sh`
- `docs/CLOSETS.md`

**Special-case files (3 files):**
- `docs/rfcs/002-source-adapter-plugin-spec.md` — sed prose, but PRESERVE `github.com/MemPalace/mempalace/*` historical issue links
- `docs/schema.sql` — header only (preserve `~/.mempalace/` legacy path comment with clarifying note)
- `CHANGELOG.md` — line 3 only (preserve all 40 historical version entries)

Preserved (DO NOT TOUCH):
- All production code (`cognitive_castle/`, `tests/`)
- `README.md` (already has correct historical acknowledgement)
- `docs/HISTORY.md`
- `docs/superpowers/{specs,plans}/`
- `website/` directory (deferred to separate PR)

Reference (read but don't modify):
- `docs/superpowers/specs/2026-05-12-mempalace-docs-sweep-design.md` (commit `614a2f21`) — source of truth, with the verbatim sed pattern set

---

## Task 1: Apply all docs sweep edits + commit

**Files:**
- Create branch: `feat/mempalace-docs-sweep` from `develop`
- Modify: 24 files per the file structure above

- [ ] **Step 1: Read the spec end-to-end**

```bash
cat docs/superpowers/specs/2026-05-12-mempalace-docs-sweep-design.md
```

Critical sections to internalize:
- "Critical: hyphen vs underscore distinction" — the context-aware sed pattern set
- Each file-by-file change list block
- The 21 acceptance criteria

- [ ] **Step 2: Create the feature branch**

```bash
git checkout develop
git pull origin develop
git checkout -b feat/mempalace-docs-sweep
git log --oneline -3
```

Expected: clean tree on `feat/mempalace-docs-sweep`, recent commits include `614a2f21` (spec final), `b00b8752`, `639517e5`, `3ebe5f08`, `0a07bb5c`.

- [ ] **Step 3: Fix CI workflows (functional bugs)**

`.github/workflows/ci.yml` — substitute `mempalace` → `cognitive_castle` (UNDERSCORE — this is the Python package name for the `--cov` flag):

```bash
sed -i 's/--cov=mempalace/--cov=cognitive_castle/g' .github/workflows/ci.yml
```

Verify:
```bash
grep -n "mempalace" .github/workflows/ci.yml
```
Expected: 0 matches.

`.github/workflows/version-guard.yml` — substitute `mempalace/version.py` → `cognitive_castle/version.py` (UNDERSCORE — actual on-disk path used by `grep`):

```bash
sed -i 's|mempalace/version\.py|cognitive_castle/version.py|g' .github/workflows/version-guard.yml
```

Verify:
```bash
grep -n "mempalace" .github/workflows/version-guard.yml
```
Expected: 0 matches.

Also verify the path actually exists:
```bash
ls cognitive_castle/version.py
```
Expected: file exists.

- [ ] **Step 4: Fix `examples/basic_mining.py` and `examples/convo_import.py`**

These are Python print-statement strings showing CLI commands. Replace `mempalace ...` with `castle ...`:

```bash
sed -i \
  -e 's/mempalace mine/castle mine/g' \
  -e 's/mempalace init/castle init/g' \
  -e 's/mempalace search/castle search/g' \
  examples/basic_mining.py examples/convo_import.py
```

Verify:
```bash
grep -n "mempalace" examples/basic_mining.py examples/convo_import.py
```
Expected: 0 matches.

- [ ] **Step 5: Fix `examples/mcp_setup.md`**

```bash
sed -i 's/mempalace-mcp/castle-mcp/g' examples/mcp_setup.md
```

Verify:
```bash
grep -n "mempalace" examples/mcp_setup.md
```
Expected: 0 matches.

- [ ] **Step 6: Fix `benchmarks/mine_bench.py` (broken Python import + fixture filename)**

Two changes needed:
1. Python imports: `from mempalace import miner` → `from cognitive_castle import miner` (UNDERSCORE — Python syntactic rule)
2. Fixture filename: `mempalace.yaml` → `castle.yaml` (new convention from PR #B's miner work)

```bash
sed -i \
  -e 's/from mempalace import miner/from cognitive_castle import miner/g' \
  -e 's/from mempalace\./from cognitive_castle./g' \
  -e 's/"mempalace\.yaml"/"castle.yaml"/g' \
  benchmarks/mine_bench.py
```

Verify:
```bash
grep -n "mempalace" benchmarks/mine_bench.py
```
Expected: 0 matches.

Quick import-sanity check (the file must at least import without `ModuleNotFoundError`):
```bash
python3 -c "import ast; ast.parse(open('benchmarks/mine_bench.py').read()); print('OK')"
```
Expected: `OK`.

- [ ] **Step 7: Bulk sweep — apply context-aware sed pattern set to the 12 bulk-sed files**

Save the pattern set to a variable for reuse:

```bash
# Apply context-aware sed to each file
for f in examples/gemini_cli_setup.md \
         benchmarks/README.md benchmarks/BENCHMARKS.md benchmarks/HYBRID_MODE.md \
         CONTRIBUTING.md AGENTS.md MISSION.md ROADMAP.md SECURITY.md \
         .devcontainer/devcontainer.json .devcontainer/post-create.sh \
         docs/CLOSETS.md; do
    sed -i \
      -e 's|https://github.com/MemPalace/mempalace|https://github.com/Testimonial/cognitive-castle|g' \
      -e 's|mempalace\.git|cognitive-castle.git|g' \
      -e 's|cd mempalace$|cd cognitive-castle|g' \
      -e 's|\bmempalace/|cognitive-castle/|g' \
      -e 's|`mempalace`|`castle`|g' \
      -e 's|mempalace mine|castle mine|g' \
      -e 's|mempalace init|castle init|g' \
      -e 's|mempalace search|castle search|g' \
      -e 's|mempalace-mcp|castle-mcp|g' \
      -e 's|MemPalace|Cognitive Castle|g' \
      "$f"
done
```

Special note: `AGENTS.md:49` has `--cov=mempalace` (in test-command documentation). The bulk sed above with `s|\bmempalace/|cognitive-castle/|g` won't catch `--cov=mempalace` (no trailing slash). Add a separate substitution:

```bash
sed -i 's/--cov=mempalace/--cov=cognitive_castle/g' AGENTS.md
```

(`--cov=` flag takes Python package name — UNDERSCORE — same as in CI workflow.)

Verify all 12 files clean:
```bash
grep -rn "mempalace\|MemPalace" examples/gemini_cli_setup.md benchmarks/README.md benchmarks/BENCHMARKS.md benchmarks/HYBRID_MODE.md CONTRIBUTING.md AGENTS.md MISSION.md ROADMAP.md SECURITY.md .devcontainer/devcontainer.json .devcontainer/post-create.sh docs/CLOSETS.md 2>&1 | head -20
```
Expected: 0 matches (or only acceptable historical references — visually inspect any matches).

- [ ] **Step 8: Defensive cleanup — fix any Python imports the bulk sed wrongly hyphenated**

Although the bulk sed is doc-focused, code blocks inside `.md` files may have been mangled. Catch any `from cognitive-castle import` (HYPHEN — Python SyntaxError) and re-fix to UNDERSCORE:

```bash
grep -rln "from cognitive-castle import\|import cognitive-castle" . --include="*.py" --include="*.md" 2>/dev/null
```

If matches appear, fix them:
```bash
grep -rln "from cognitive-castle import\|import cognitive-castle" . --include="*.py" --include="*.md" 2>/dev/null | xargs -r sed -i \
  -e 's|from cognitive-castle import|from cognitive_castle import|g' \
  -e 's|import cognitive-castle|import cognitive_castle|g'
```

Verify:
```bash
grep -rn "from cognitive-castle import\|import cognitive-castle" . --include="*.py" --include="*.md" 2>/dev/null
```
Expected: 0 matches.

- [ ] **Step 9: Handle `examples/HOOKS_TUTORIAL.md` (doubly broken — needs care)**

The tutorial references `mempal_save_hook.sh` and `mempal_precompact_hook.sh` shell scripts that don't exist. The current correct hook scripts are `castle-stop-hook.sh` and `castle-precompact-hook.sh` in `.claude-plugin/hooks/`.

Recommended approach: **simplify the tutorial to point at the plugin install path** (the recommended way to use Castle in Claude Code now), and keep the manual config as a fallback/advanced section.

Read the current file first:
```bash
cat examples/HOOKS_TUTORIAL.md
```

Apply two layers of fixes:

**Layer 1 — script name fixes** (if you keep the manual config section):

```bash
sed -i \
  -e 's/mempal_save_hook\.sh/castle-stop-hook.sh/g' \
  -e 's/mempal_precompact_hook\.sh/castle-precompact-hook.sh/g' \
  examples/HOOKS_TUTORIAL.md
```

**Layer 2 — brand + command + env var updates**:

```bash
sed -i \
  -e 's|mempalace mine|castle mine|g' \
  -e 's|mempalace init|castle init|g' \
  -e 's|MemPalace hooks|Cognitive Castle hooks|g' \
  -e 's|MemPalace repository|Cognitive Castle repository|g' \
  -e 's|MemPalace|Cognitive Castle|g' \
  -e 's|MEMPALACE_PYTHON|CASTLE_PYTHON|g' \
  -e 's|MEMPAL_DIR|CASTLE_DIR|g' \
  -e 's|`mempalace`|`castle`|g' \
  examples/HOOKS_TUTORIAL.md
```

**Layer 3 — optional simplification**: read the file again after sed. If the manual config still feels like the primary path, consider adding a prominent note at the top:

```markdown
> **Recommended:** install Castle via Claude Code's plugin marketplace instead of the manual config below:
> ```
> /plugin marketplace add Testimonial/cognitive-castle
> /plugin install castle@cognitive-castle
> ```
> The plugin auto-registers the Stop + PreCompact hooks. The manual config below is documented for users who need fine-grained control or for non-Claude-Code agents.
```

Implementer judgment: add the prominent note if the file still flows well. Skip if the simple sed-only approach already produces a coherent doc.

Verify:
```bash
grep -n "mempalace\|MemPalace\|mempal_save\|mempal_precompact" examples/HOOKS_TUTORIAL.md
```
Expected: 0 matches.

- [ ] **Step 10: Handle `integrations/openclaw/SKILL.md` (full plugin metadata sweep)**

This file's frontmatter has 6+ mempalace references using different forms. Apply targeted edits:

Use the `Edit` tool with `replace_all=False` for each unique substitution. Read the file first:
```bash
cat integrations/openclaw/SKILL.md
```

Then apply edits (one for each unique pattern, since the same word `mempalace` appears in different contexts):

```yaml
# Frontmatter edits:
name: mempalace                          → name: castle
description: "MemPalace — Local AI ...   → description: "Cognitive Castle — Local AI ...
homepage: https://github.com/MemPalace/mempalace → homepage: https://github.com/Testimonial/cognitive-castle
- mempalace  (anyBins section)           → - castle
id: mempalace-pip                        → id: castle-pip
label: "Install MemPalace (Python, local ChromaDB)" → label: "Install Cognitive Castle (Python, local LanceDB)"
package: mempalace                       → package: cognitive-castle  (PyPI dist name, HYPHEN)
- mempalace  (bins section)              → - castle
```

Body section:
- `# MemPalace — Local AI Memory System` → `# Cognitive Castle — Local AI Memory System`
- Any `mempalace ...` command examples → `castle ...`
- Any `MemPalace` prose mentions → `Cognitive Castle`
- Any references to `chromadb` should become `lancedb` (chroma was removed in PR #8)

Implementer should pragmatically use sed for the frontmatter since each `mempalace` appears once per context:

```bash
sed -i \
  -e 's|name: mempalace|name: castle|g' \
  -e 's|MemPalace — Local AI|Cognitive Castle — Local AI|g' \
  -e 's|MemPalace |Cognitive Castle |g' \
  -e 's|https://github.com/MemPalace/mempalace|https://github.com/Testimonial/cognitive-castle|g' \
  -e 's|^        - mempalace$|        - castle|g' \
  -e 's|id: mempalace-pip|id: castle-pip|g' \
  -e 's|package: mempalace|package: cognitive-castle|g' \
  -e 's|Install MemPalace|Install Cognitive Castle|g' \
  -e 's|local ChromaDB|local LanceDB|g' \
  -e 's|mempalace mine|castle mine|g' \
  -e 's|mempalace init|castle init|g' \
  -e 's|`mempalace`|`castle`|g' \
  integrations/openclaw/SKILL.md
```

Verify:
```bash
grep -n "mempalace\|MemPalace\|ChromaDB" integrations/openclaw/SKILL.md
```
Expected: 0 matches.

- [ ] **Step 11: Decide on `.agents/plugins/marketplace.json` (delete or update)**

This file points at `./.codex-plugin/` which was deleted in PR #8. The whole file is referring to dead infrastructure.

Check if anything consumes this file:
```bash
grep -rn "\.agents/plugins/marketplace" . --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=test_env --exclude-dir=.echelon 2>/dev/null
```

If the only matches are inside the spec/plan docs themselves (no production consumer), **delete the file**:

```bash
git rm .agents/plugins/marketplace.json
# Optionally also remove the now-empty parent if it has nothing else:
if [ -z "$(ls .agents/plugins/ 2>/dev/null)" ]; then
  rmdir .agents/plugins/
fi
if [ -z "$(ls .agents/ 2>/dev/null)" ]; then
  rmdir .agents/
fi
```

If a real consumer exists (e.g., a `.agents/` runtime), **update the file** instead:
```json
{
  "name": "castle",
  "interface": {
    "displayName": "Cognitive Castle"
  },
  "plugins": [
    {
      "name": "castle",
      "source": {
        "source": "local",
        "path": "./.claude-plugin"
      },
      "policy": {
        "installation": "AVAILABLE",
        "authentication": "NONE"
      },
      "category": "Coding"
    }
  ]
}
```

Default: delete (no consumer found).

- [ ] **Step 12: Handle `docs/rfcs/002-source-adapter-plugin-spec.md` (preserve historical issue links)**

This file has both:
- Body text using `mempalace mine`, `pip install mempalace-source-X`, brand mentions — UPDATE
- Historical GitHub issue links at `github.com/MemPalace/mempalace/issues/X` and `pulls/X` — PRESERVE

Strategy: apply the context-aware sed pattern set, but the bulk pattern `s|https://github.com/MemPalace/mempalace|https://github.com/Testimonial/cognitive-castle|g` would rewrite the historical links — that's wrong for this file.

Use a more surgical sed that ONLY touches non-link contexts:

```bash
# Apply prose-only updates (NOT the GitHub URL rewrite):
sed -i \
  -e 's|mempalace mine|castle mine|g' \
  -e 's|`mempalace`|`castle`|g' \
  -e 's|pip install mempalace-source-|pip install cognitive-castle-source-|g' \
  -e 's|MemPalace source adapters|Cognitive Castle source adapters|g' \
  -e 's|MemPalace to function|Cognitive Castle to function|g' \
  -e 's|MemPalace's|Cognitive Castle's|g' \
  -e 's|MemPalace |Cognitive Castle |g' \
  -e 's|\bmempalace/mine\b|castle mine|g' \
  docs/rfcs/002-source-adapter-plugin-spec.md
```

After sed, verify historical links are preserved:
```bash
grep -c "github.com/MemPalace/mempalace" docs/rfcs/002-source-adapter-plugin-spec.md
```
Expected: > 0 (the historical issue/PR links survive).

```bash
grep -n "mempalace\|MemPalace" docs/rfcs/002-source-adapter-plugin-spec.md | grep -v "github.com/MemPalace"
```
Expected: 0 matches (no non-link `mempalace`/`MemPalace` left).

If any prose still has stale brand references that the sed missed (e.g., "MemPalace's" with curly apostrophe), fix manually with `Edit`.

- [ ] **Step 13: Update `docs/schema.sql` header (preserve legacy path note)**

Use `Edit`:
```sql
-- Before:
-- MemPalace Knowledge Graph Schema
-- SQLite database at ~/.mempalace/knowledge_graph.db

-- After:
-- Cognitive Castle Knowledge Graph Schema
-- SQLite database at ~/.castle/knowledge_graph.db (legacy fallback: ~/.mempalace/knowledge_graph.db)
```

Verify:
```bash
grep -n "MemPalace\|mempalace" docs/schema.sql
```
Expected: 1 match (the legacy fallback path comment, intentional).

- [ ] **Step 14: Update `CHANGELOG.md` line 3 (preserve entries)**

Use `Edit`. Find line 3:
```bash
sed -n '3p' CHANGELOG.md
```

Then edit just line 3:
```markdown
# Before:
All notable changes to [MemPalace](https://github.com/MemPalace/mempalace) are documented in this file.

# After:
All notable changes to [Cognitive Castle](https://github.com/Testimonial/cognitive-castle) (formerly MemPalace) are documented in this file.
```

Verify:
```bash
sed -n '3p' CHANGELOG.md
# Should print the new line.

grep -c "MemPalace\|mempalace" CHANGELOG.md
# Should be 40 (down from 41; only line 3 changed, all entries preserved).
```

- [ ] **Step 15: Final scope adherence + production check**

```bash
# No production code modified:
git diff --name-only develop..HEAD | grep -E "^(cognitive_castle|tests)/"
```
Expected: empty.

```bash
# README.md unchanged:
git diff develop..HEAD -- README.md | head -3
```
Expected: empty.

```bash
# docs/HISTORY.md unchanged:
git diff develop..HEAD -- docs/HISTORY.md | head -3
```
Expected: empty.

```bash
# docs/superpowers/ unchanged:
git diff --name-only develop..HEAD | grep "^docs/superpowers/"
```
Expected: empty.

```bash
# website/ unchanged:
git diff --name-only develop..HEAD | grep "^website/"
```
Expected: empty.

```bash
# Production brand strings preserved (still using "cognitive-castle"):
grep -c '"cognitive-castle"' cognitive_castle/cli.py cognitive_castle/miner.py cognitive_castle/convo_miner.py cognitive_castle/mcp_server.py
```
Expected: ≥ 5 matches across these files.

- [ ] **Step 16: Run focused test suite**

```bash
pytest tests/ --ignore=tests/benchmarks -q --tb=no 2>&1 | tail -3
```
Expected: failed ≤ 65 (post-#C baseline). No tests were modified, so this is sanity only.

- [ ] **Step 17: Commit**

```bash
git add .
git commit -m "$(cat <<'EOF'
docs: mempalace docs sweep (PR #D — final cleanup)

Per spec docs/superpowers/specs/2026-05-12-mempalace-docs-sweep-design.md
(commit 614a2f21):

Critical functional fixes:
- .github/workflows/ci.yml: --cov=mempalace → --cov=cognitive_castle
  (CI coverage check was silently broken — referenced nonexistent
  package)
- .github/workflows/version-guard.yml: 4 paths from
  mempalace/version.py → cognitive_castle/version.py
- examples/{basic_mining,convo_import}.py: print statements showing
  `mempalace ...` commands → `castle ...`
- examples/mcp_setup.md: mempalace-mcp → castle-mcp (nonexistent
  binary)
- examples/HOOKS_TUTORIAL.md: refs to nonexistent
  mempal_save_hook.sh / mempal_precompact_hook.sh →
  castle-stop-hook.sh / castle-precompact-hook.sh; updated commands
  + env vars
- benchmarks/mine_bench.py: `from mempalace import miner` was
  ModuleNotFoundError → `from cognitive_castle import miner`;
  fixture writes castle.yaml not mempalace.yaml
- .agents/plugins/marketplace.json: deleted (pointed to deleted
  .codex-plugin/, no consumer found)
- integrations/openclaw/SKILL.md: full plugin metadata sweep —
  name/description/bins/package/install fields, plus ChromaDB →
  LanceDB (chroma was removed in PR #8)

Brand updates (current-tense statements):
- CONTRIBUTING.md, AGENTS.md, MISSION.md, ROADMAP.md, SECURITY.md
- benchmarks/{README,BENCHMARKS,HYBRID_MODE}.md
- .devcontainer/{devcontainer.json,post-create.sh}
- docs/CLOSETS.md, docs/rfcs/002-source-adapter-plugin-spec.md,
  docs/schema.sql header
- CHANGELOG.md line 3 only (all 40 entries preserved as historical)
- examples/gemini_cli_setup.md

Preserved (unchanged):
- README.md (historical acknowledgement at line 345)
- docs/HISTORY.md (historical narrative)
- docs/superpowers/ (frozen design history)
- website/ (deferred to separate PR)
- CHANGELOG.md entries (40 of 41 refs)
- docs/rfcs/002 GitHub issue links to MemPalace/mempalace
  (historical references to upstream org)
- docs/schema.sql legacy ~/.mempalace/ path comment
- Production code (cognitive_castle/, tests/) — including the
  literal "cognitive-castle" brand strings at cli.py:993,
  miner.py:989/1044, convo_miner.py:383, mcp_server.py:1643

Final PR of the 4-PR cleanup series:
- #A: SOAR removal (PR #14)
- #B: Mempalace production fixes (PR #15)
- #C: Mempalace tests sweep (PR #16)
- #D: This PR — mempalace docs sweep

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 18: Report ready for Task 2**

Report:
- Branch: `feat/mempalace-docs-sweep`
- Commit SHA
- Files modified (should be ~24)
- Any special-case decisions (e.g., what happened to `.agents/plugins/marketplace.json` — deleted or updated?)
- Whether HOOKS_TUTORIAL.md got the simplification note
- Confirmation: production code untouched, README untouched, docs/HISTORY untouched, docs/superpowers untouched, website/ untouched
- Focused suite count

---

## Task 2: Verify 21 ACs + push + open PR

**Files:**
- Read-only verification; surgical fix if any AC fails.

- [ ] **Step 1: AC1-2 — CI workflows fixed**

```bash
grep -c "mempalace" .github/workflows/ci.yml      # expect 0
grep -c "mempalace" .github/workflows/version-guard.yml  # expect 0
grep -c "cognitive_castle" .github/workflows/version-guard.yml  # expect ≥ 4
```

- [ ] **Step 2: AC3 — examples use working commands**

```bash
grep -rn "mempalace (init|mine|search)|mempalace-mcp|MEMPALACE_PYTHON" examples/ 2>/dev/null
```
Expected: 0 matches.

```bash
grep -rn "castle (init|mine|search)|castle-mcp" examples/ 2>/dev/null | wc -l
```
Expected: ≥ 5 (commands appear across the examples).

- [ ] **Step 3: AC4 — top-level docs**

```bash
grep -rn "mempalace\|MemPalace" CONTRIBUTING.md AGENTS.md MISSION.md ROADMAP.md SECURITY.md 2>/dev/null | head -5
```
Expected: 0 matches.

- [ ] **Step 4: AC5 — benchmarks docs**

```bash
grep -rn "mempalace\|MemPalace" benchmarks/README.md benchmarks/BENCHMARKS.md benchmarks/HYBRID_MODE.md 2>/dev/null | head -5
```
Expected: 0 matches.

- [ ] **Step 5: AC6 — devcontainer**

```bash
grep -rn "mempalace\|MemPalace" .devcontainer/devcontainer.json .devcontainer/post-create.sh 2>/dev/null
```
Expected: 0 matches.

```bash
grep '"name"' .devcontainer/devcontainer.json
```
Expected: `"name": "Cognitive Castle",`.

- [ ] **Step 6: AC7 — docs/CLOSETS.md**

```bash
grep -n "mempalace\|MemPalace" docs/CLOSETS.md
```
Expected: 0 matches.

- [ ] **Step 7: AC8 — docs/rfcs/002 (historical links preserved)**

```bash
# Body / prose has no current-tense MemPalace:
grep -n "mempalace\|MemPalace" docs/rfcs/002-source-adapter-plugin-spec.md | grep -v "github.com/MemPalace"
```
Expected: 0 matches.

```bash
# Historical GitHub links preserved:
grep -c "github.com/MemPalace/mempalace" docs/rfcs/002-source-adapter-plugin-spec.md
```
Expected: ≥ 5 (the historical issue/PR links survive).

- [ ] **Step 8: AC9 — docs/schema.sql header**

```bash
head -3 docs/schema.sql
```
Expected: header line says "Cognitive Castle Knowledge Graph Schema" + path line mentions both `~/.castle/` and legacy `~/.mempalace/`.

- [ ] **Step 9: AC10 — CHANGELOG line 3 + entries preserved**

```bash
sed -n '3p' CHANGELOG.md | grep -c "Cognitive Castle"
```
Expected: 1.

```bash
grep -c "MemPalace\|mempalace" CHANGELOG.md
```
Expected: 40 (line 3 updated, 40 historical entries preserved).

- [ ] **Step 10: AC11 — README untouched**

```bash
git diff develop..HEAD -- README.md | head -3
```
Expected: empty.

- [ ] **Step 11: AC12 — docs/HISTORY untouched**

```bash
git diff develop..HEAD -- docs/HISTORY.md | head -3
```
Expected: empty.

- [ ] **Step 12: AC13 — docs/superpowers untouched**

```bash
git diff --name-only develop..HEAD | grep "^docs/superpowers/"
```
Expected: empty.

- [ ] **Step 13: AC14 — focused suite stable**

```bash
pytest tests/ --ignore=tests/benchmarks -q --tb=no 2>&1 | tail -3
```
Expected: failed ≤ 65.

- [ ] **Step 14: AC15-17 — HOOKS_TUTORIAL.md / convo_import.py / mine_bench.py**

```bash
# Hook script names correct:
grep -n "castle-stop-hook\|castle-precompact-hook\|mempal_" examples/HOOKS_TUTORIAL.md
```
Expected: matches for `castle-stop-hook` and `castle-precompact-hook`; 0 matches for `mempal_`.

```bash
# convo_import.py + mine_bench.py use new names:
grep -n "from mempalace\|mempalace mine\|mempalace.yaml" examples/convo_import.py benchmarks/mine_bench.py
```
Expected: 0 matches.

- [ ] **Step 15: AC18 — .agents/plugins/marketplace.json resolved**

```bash
ls .agents/plugins/marketplace.json 2>&1
```
Expected: either "No such file" (deleted) OR file exists with `castle` references.

- [ ] **Step 16: AC19 — integrations/openclaw/SKILL.md updated**

```bash
grep -n "mempalace\|MemPalace\|ChromaDB" integrations/openclaw/SKILL.md
```
Expected: 0 matches.

```bash
grep -n "name: castle\|cognitive-castle\|Cognitive Castle" integrations/openclaw/SKILL.md | head -5
```
Expected: matches.

- [ ] **Step 17: AC20 — website/ untouched**

```bash
git diff --name-only develop..HEAD | grep "^website/"
```
Expected: empty.

- [ ] **Step 18: AC21 — production brand strings preserved**

```bash
grep -c '"cognitive-castle"' cognitive_castle/cli.py cognitive_castle/miner.py cognitive_castle/convo_miner.py cognitive_castle/mcp_server.py
```
Expected: 5+ matches (these are intentional brand strings, not modified).

```bash
git diff --name-only develop..HEAD | grep -E "^(cognitive_castle|tests)/"
```
Expected: empty (no production code modified).

- [ ] **Step 19: Push branch**

```bash
git push -u origin feat/mempalace-docs-sweep
```

- [ ] **Step 20: Open the PR**

```bash
gh pr create --base develop --title "docs: mempalace docs sweep (PR #D — final cleanup)" --body "$(cat <<'EOF'
## Summary

Final PR of the 4-PR cleanup series. Fixes broken CI workflows + example commands + benchmark imports, plus brand-update sweep across top-level repo docs, benchmarks, devcontainer, RFC 002, and CLOSETS.md.

Per spec [\`2026-05-12-mempalace-docs-sweep-design.md\`](docs/superpowers/specs/2026-05-12-mempalace-docs-sweep-design.md) (commit 614a2f21).

## Critical functional fixes

- **CI workflows were silently broken**: \`--cov=mempalace\` and \`mempalace/version.py\` referenced paths that don't exist post-rebrand. Every prior PR's UNSTABLE CI is partly explained by these. Now fixed.
- **Examples told users to run nonexistent commands**: \`mempalace init/mine/search\`, \`mempalace-mcp\`, \`mempal_save_hook.sh\`. Now use real names (\`castle ...\`, \`castle-mcp\`, \`castle-stop-hook.sh\`).
- **\`benchmarks/mine_bench.py\` raised \`ModuleNotFoundError\` on import** (\`from mempalace import miner\`). Now correctly imports \`from cognitive_castle import miner\`.
- **\`.agents/plugins/marketplace.json\` pointed at deleted \`.codex-plugin/\`** — file resolved (deleted or updated).
- **\`integrations/openclaw/SKILL.md\` plugin metadata** — full sweep including \`bins\`/\`package\`/\`install\` fields + ChromaDB→LanceDB (chroma was removed in PR #8).

## Brand updates

Top-level docs, benchmarks, devcontainer, docs/CLOSETS.md, docs/rfcs/002 (body only — preserved historical \`MemPalace/mempalace\` issue links), docs/schema.sql header, CHANGELOG.md line 3.

## Preserved

- \`README.md\` (historical acknowledgement)
- \`docs/HISTORY.md\` (historical narrative)
- \`docs/superpowers/\` (frozen design history)
- \`website/\` (deferred to separate PR)
- CHANGELOG entries (40 of 41 refs — only present-tense intro changed)
- docs/rfcs/002 GitHub historical issue links (\`MemPalace/mempalace/issues/X\`)
- docs/schema.sql legacy path comment (with clarifying note)
- Production code including the literal \`"cognitive-castle"\` brand strings at \`cli.py:993\`, \`miner.py:989/1044\`, \`convo_miner.py:383\`, \`mcp_server.py:1643\` (these ARE correct — PyPI distribution name as agent identifier / MCP server name)

## Doc path convention

User decision (recorded during spec review): doc prose uses the **hyphenated** form (\`cognitive-castle/searcher.py\`) for brand consistency, even though the actual on-disk path is \`cognitive_castle/\` (underscore — Python module name). Python \`import\` statements MUST use underscore (language rule).

## Series complete

- ✅ #A: SOAR removal (PR #14)
- ✅ #B: Mempalace production fixes (PR #15)
- ✅ #C: Mempalace tests sweep (PR #16)
- ✅ **#D: This PR — mempalace docs sweep**

## Test plan

- [x] All 21 ACs from spec verified (CI workflow fixes, file-by-file grep, preservation diffs, production-code-untouched, focused-suite stable)
- [x] Production string-literal \`"cognitive-castle"\` references preserved
- [x] No production code (\`cognitive_castle/\`, \`tests/\`) modified
- [x] \`website/\` directory NOT modified
- [x] Focused suite: failed ≤ 65

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 21: Report status**

Report:
- PR URL
- All 21 AC results PASS/FAIL
- Final focused-suite numbers
- Any AC fixes made (with brief description)

User merges if happy.

---

## Self-Review

**Spec coverage:**
- AC1-2 (CI workflows) → Task 1 Step 3 + Task 2 Step 1 ✓
- AC3 (examples) → Task 1 Steps 4, 5, 6, 9 + Task 2 Step 2 ✓
- AC4 (top-level docs) → Task 1 Step 7 + Task 2 Step 3 ✓
- AC5 (benchmarks) → Task 1 Steps 6, 7 + Task 2 Step 4 ✓
- AC6 (devcontainer) → Task 1 Step 7 + Task 2 Step 5 ✓
- AC7 (docs/CLOSETS.md) → Task 1 Step 7 + Task 2 Step 6 ✓
- AC8 (docs/rfcs/002) → Task 1 Step 12 + Task 2 Step 7 ✓
- AC9 (docs/schema.sql) → Task 1 Step 13 + Task 2 Step 8 ✓
- AC10 (CHANGELOG) → Task 1 Step 14 + Task 2 Step 9 ✓
- AC11 (README untouched) → Task 1 Step 15 + Task 2 Step 10 ✓
- AC12 (docs/HISTORY untouched) → Task 1 Step 15 + Task 2 Step 11 ✓
- AC13 (docs/superpowers untouched) → Task 1 Step 15 + Task 2 Step 12 ✓
- AC14 (focused suite stable) → Task 1 Step 16 + Task 2 Step 13 ✓
- AC15-17 (HOOKS_TUTORIAL / convo / bench) → Task 1 Steps 6, 9 + Task 2 Step 14 ✓
- AC18 (.agents/plugins/marketplace.json) → Task 1 Step 11 + Task 2 Step 15 ✓
- AC19 (openclaw SKILL.md) → Task 1 Step 10 + Task 2 Step 16 ✓
- AC20 (website/ untouched) → Task 1 Step 15 + Task 2 Step 17 ✓
- AC21 (production brand strings preserved) → Task 1 Step 15 + Task 2 Step 18 ✓

All 21 ACs mapped to verification steps.

**Placeholder scan:**
- The .agents/plugins/marketplace.json decision (delete-vs-update) is delegated with explicit decision criteria in Task 1 Step 11 — concrete, not a placeholder.
- The HOOKS_TUTORIAL.md simplification note is described as "implementer judgment" but with explicit conditions ("if the file still flows well after sed") — acceptable judgment delegation.
- No "TBD" / "TODO" / "implement later".

**Type consistency:**
- N/A (docs sweep, no types).

Plan complete and ready for execution.
