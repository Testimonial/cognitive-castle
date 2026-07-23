# Cognitive Castle Roadmap

_Last refreshed: 2026-07-23. Current release: [v3.4.0](https://github.com/Testimonial/cognitive-castle/releases/tag/v3.4.0)._

## Shipped in v3.4.0 (this release)

- **LanceDB backend** replacing upstream Chroma
- **3-stage retrieval pipeline** — dense (bge-m3) + Tantivy FTS + KG-hop → weighted RRF + recency → cross-encoder rerank (bge-reranker-v2-m3)
- **Stage 4 LLM-as-judge**, **Stage 5 SOAR symbolic re-ranking**, **Stage 6 deterministic quality re-rank** (via vendored `understanding` package). Selectable via `castle search --mode {fast|standard|boosted|max}`
- **Claude Code plugin** — auto-registers MCP server + Stop / PreCompact background-mining hooks
- **MCP `initialize.instructions` injection** — bakes `PALACE_PROTOCOL` + AAAK spec + live palace state into the client's system prompt at session start
- **`claude-cli` LLM provider** — reuses parent Claude Code's auth for Stage 4 judge, no separate `ANTHROPIC_API_KEY` required
- **Research subproject** — an information-theoretic study of verbatim personal memory. Full pipeline, 108 unit tests, paper draft. First full-palace headline: ρ(nn_novelty, LLE_residual) = 0.9820 on 65,779 drawers across 7 wings.

Full detail: [CHANGELOG.md](CHANGELOG.md#340--2026-07-23).

## Next up (unversioned; ordered by likelihood)

- **PyPI publication** — `pip install cognitive-castle` currently 404s. The `Publish to PyPI` GitHub Actions workflow is now committed (see [docs/RELEASING.md](docs/RELEASING.md)); it will run and succeed once Trusted Publishing is configured at pypi.org (one-time human step: add the trusted-publisher pointing at `Testimonial/cognitive-castle` + `publish.yml` + `pypi` environment, then re-tag or rerun the workflow).
- **Estimator C (`llm_surprise`) full-palace numbers** — 925-drawer stratified subsample running via `claude-cli`. Landing this closes the paper's headline `A↔C` and `B↔C` correlation claims and unblocks a v3.5.0 release with the completed research artifact.
- **H3 downstream R@5 evaluation** — validates the paper's applied claim: do info-scores predict retrieval utility? Runs on LongMemEval; deferred to future work per the current preprint's Limitations section.
- **Cross-user validation** — the v3.4.0 research is n=1 (one palace). Recruiting a second, structurally-different palace for reproducibility is the highest-value single validation step.
- **Docs surface consolidation** — the recent audit (PRs #60, #61) hit the top-level README + 15 Priority-1 files. The `website/` subtree has confirmed drift of the same kind and needs its own PR.
- **CI red on develop for pre-existing failures** (test-linux 3.9 setup errors, macOS/Windows lint) — these have been red for 3+ months and no dependabot bump can go through with green checks. Getting to green is a modest cleanup, but signals maintenance discipline.
- **`castle-info-theory` CLI runnable end-to-end** — the current `run_experiment.py` driver works but the STAGES-based `castle-info-theory run --all` path has no `run_default` entry-points wired. Either add them or archive the STAGES registry.
- **Cross-encoder swap sensitivity study** — `mxbai-rerank-large-v2` outperforms `bge-reranker-v2-m3` on English MTEB but is English-only. A controlled cross-lingual comparison would settle whether the default should change. (Currently deferred; burden-of-proof on any future swap is on cross-lingual perf.)

## Branch model

```
develop     ← the default branch; PRs merge here, releases tag here
feature/*   ← short-lived branches, merged and deleted via
              `gh pr merge --merge --delete-branch`
```

There is no `main` — `develop` is the release branch (`v3.4.0` was tagged on develop).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). PRs target `develop`. Design principles from [CLAUDE.md](CLAUDE.md#design-principles) are non-negotiable — verbatim always, incremental only, entity-first, local-first, zero external API by default.
