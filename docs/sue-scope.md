# SUE, requirements, and Castle memory

SUE analyzes software specifications and the consequences of interpreting their
requirements. It does **not** independently establish factual truth, inspect a
running application, or validate every record in a memory palace. Cognitive
Castle now includes a source-scoped SUE adapter, callable through its CLI and
MCP tools. It reviews explicitly selected drawers on demand; ordinary ingestion
and retrieval do not trigger model calls or acquire truth labels.

## Run a Castle review now

Use `castle_search` to locate the requirements, then `castle_get_drawer` to check
their exact content and IDs. Include definitions, exceptions, and relevant
historical/revision context. Select the bounded specification deliberately;
retrieval ranking alone is not a reliable specification boundary.

```bash
# Default: local Ollama on http://127.0.0.1:11434, qwen3.5:latest.
castle sue review --drawer DRAWER_ID --drawer CONTEXT_DRAWER_ID \
  --decision "What does enabled mean, and when is an audit event required?"

# Read the saved run; no new model call. Omit RUN_ID to list recent runs.
castle sue status RUN_ID

# Explicit external processing of this selected bundle through Codex.
castle sue review --drawer DRAWER_ID --decision "What does enabled mean?" \
  --provider codex --model gpt-5.6-luna --lens parmenides --wait

# A different palace: put the global option before the command.
castle --palace /path/to/palace sue status
```

Install/run the selected Ollama model separately, or use your installed and
authenticated Codex CLI. No model download, external fallback, or provider
change happens silently. This adapter currently supports these two transports;
it deliberately ignores ambient `CASTLE_LLM_*`, `ECHELON_LLM`, and Codex markers
for provider/endpoint selection. Supply `--model` for a different local model.
Codex runs in an isolated reader context with tools, project instructions,
memory and MCP disabled; the provider remains external.

MCP equivalents (tool arguments):

```json
{"name":"castle_sue_review","arguments":{"drawer_ids":["DRAWER_ID"],"decision":"What does enabled mean?","provider":"ollama","lens":"euthyphro"}}
{"name":"castle_sue_status","arguments":{"run_id":"RUN_ID"}}
```

Restart an existing Castle MCP connection after installing this code. The review
tool returns a run ID immediately after snapshotting selected drawers; a worker
does the model calls. Status without a run ID lists the last 20 reviews and all
nine lenses: Euthyphro, Meno, Parmenides, Cratylus, Theaetetus, Sophist, Gorgias,
Republic, and Philebus. One run uses one selected lens, not nine model campaigns.

The default budget is seven turns, at most two provider attempts per turn, and
120 seconds per attempt. `--max-turns` accepts 1–14; `--timeout` accepts 1–300.
A short budget can produce `BOUNDED_STOP`, which is not a substantive verdict.
Local model output is validated against the same evidence/turn contract as
Codex output. Invalid output gets one corrective retry, then the partial trace
and call evidence remain available with `status=failed`.

Each run is saved under `<palace>/.sue/runs/<RUN_ID>/`:

- `source-001.txt`, etc.: exact UTF-8 drawer text, including original whitespace.
- `specification.txt`: the selected text with labeled source/context boundaries.
- `manifest.json`: ordered drawer IDs, full source metadata (including revision
  and supersession labels when present), SHA-256 hashes, byte/line mappings,
  the stated decision, provider/model and call limits, plus engine provenance.
- `report.md` and `trace.json`: the dialogue, current-claim understanding profile,
  unresolved questions, explicit/inferred/assumed premises, revisions, stop
  reason, and citation links back to drawer IDs and hashes.
- `calls/`: outputs and validation/transport evidence for every provider attempt.
- `state.json` and `worker.log`: execution status and launch/runtime diagnostics.

Files are separate derived review records in the same palace. They are retrieved
through SUE status, not inserted into the drawer search index as original memory.
Every rerun has a new identity. Snapshot hashes are checked before a model call;
source drawers are never rewritten. Findings concern those frozen revisions:
editing or deleting a drawer later does not update an earlier finding. Start a
new review for a new revision. Interrupted workers are reported as interrupted;
there is no automatic provider retry across runs.

The bundled engine is the repaired Echelon `a4286d83` dialectic implementation
(policy `2026-09-24`, trace schema 2). Its four source files are preserved
byte-for-byte with hashes and MIT license in
[`cognitive_castle/_vendor/sue/`](../cognitive_castle/_vendor/sue/UPSTREAM.json).
Castle adds an explicit per-operator response instruction for smaller models;
the trace records this prompt policy. Upstream validation and dialogue routing
are unchanged. A successful provider call can still be rejected by validation.
The seven profile dimensions are definition, distinctions, criterion/cause,
division into cases, counterexample, consequences, and the opposite hypothesis.
`RESOLVED` means this model run examined the required dimensions of its current
claim; it is not certified human understanding or a truth score.

## What the September 24, 2026 diagnostic actually did

The standalone `sue_challenge.py` from
[Echelon PR #172](https://github.com/B3Cognition/echelon/pull/172) was run without
modifying its implementation. The input was an exact copy of Castle's README
at commit `2783c34070c91b3ed8b64693e169a68bdfd9e59c`; the SUE checkout was
`f40c0e87c88851422baf01651047b5ea77c933a5`.

The Codex run requested `gpt-5.6-luna` with `low` reasoning effort, six questions,
one attempt per round, and a 120-second timeout per model call. Both calls
succeeded. The CLI did not separately report the resolved model identity.

1. Round 1 read the README and proposed questions about its ambiguities,
   assumptions, and possible contradictions.
2. Round 2 received the README and those questions in a fresh context, and
   answered using only that document.
3. SUE labeled one answer `CONTRADICTED` and five `UNANSWERABLE`.
4. The coding assistant subsequently checked those suggestions against source
   code. This was a separate review, not a capability added to SUE.

SUE received no drawers, Castle search results, knowledge-graph records, or
implementation files. Castle MCP, memory, tools, and project instructions were
disabled in the Codex reader. An earlier Claude diagnostic was separate from
this Codex run. No memory content was exported to either diagnostic.

The README mixes product claims, examples, setup instructions, and architecture.
It is not a curated behavioral requirements specification. This was therefore an
**exploratory README review**, not a validated requirements-readiness result or
an audit of the palace's contents. There was no consensus/reproducibility
campaign and no measurement of SUE's factual accuracy.

One example shows the distinction: SUE questioned whether growing palace
history could fit inside 2.3 GB. The README assigned that figure to embedding
model weights, not database capacity. That question's premise was mistaken.
Conversely, checking the analyzer confirmed 34 metrics where the README said
31; that confirmation came from code inspection and execution, not from SUE.

## Requirements need not already be clear

SUE is intended to expose unclear, underspecified, or incompatible requirements.
A requirement can be ambiguous and still be a suitable input. The important
boundary is its role: it states expected behavior for an identified system and
decision. A recollection, prediction, question, example, or obsolete design is
not automatically a current requirement.

The v1 challenge accepts Markdown prose, including passages without requirement
IDs. Accepting that input does not make every passage normative or validate the
use of its verdicts as truth labels. For intended scope and authority, see the
[SUE specification at the audited commit](https://github.com/B3Cognition/echelon/blob/f40c0e87c88851422baf01651047b5ea77c933a5/docs/socratic-understanding/SPECIFICATION.md).
It explicitly excludes implementation correctness and majority agreement as
proof of truth.

## Three different checks

| Check | Evidence | What it can establish |
|---|---|---|
| Verbatim preservation | Original source, exact stored text, revisions, hashes | Whether the stored passage matches its source; not whether the speaker was right |
| Claim consistency | Dated source records, entity identity, graph relationships, and relevant external evidence when explicitly authorized | Support, conflict, or missing evidence within the checked scope |
| Requirement interpretation with SUE | A bounded specification and its source references | Questions about ambiguity, missing conditions, and incompatible interpretations; not whether the implementation satisfies the requirements |

Castle already has a temporal SQLite knowledge graph and
[`fact_checker.py`](../cognitive_castle/fact_checker.py). The checker detects
similar registered names, mismatched relationships, and stale relationships
against local records. Its relationship extraction uses narrow English
patterns. An empty findings list means no supported issue was detected; it
cannot certify arbitrary conversation text as true, and the graph itself can
contain mistakes.

Castle's **five layers / 34 metrics** in the vendored `understanding` analyzer
measure text and specification quality. They are separate from SUE, from the
fact checker, and from the four-layer L0–L3 memory wake-up stack. A high quality
score or high novelty score is not evidence that a claim is true.

## Where SUE fits in the proposed five evidence checks

These are verification responsibilities, not the existing five quality layers.

| Check | Castle responsibility / current boundary |
|---|---|
| 1. Source fidelity | Exact drawer snapshots and hashes; originals remain unchanged |
| 2. Attribution and scope | Preserve source metadata/revisions; the caller selects requirements and context; the adapter does not infer normative authority |
| 3. Factual consistency | Existing local fact checker / temporal graph, with the limitations above; SUE does not replace them |
| 4. Depth of requirement interpretation | **Implemented here:** selected Castle drawers → bounded SUE dialogue → source-linked derived report in Castle |
| 5. Implementation evidence | Separate code inspection and executed tests at a recorded commit; automatic requirement → function → test graph is still future work |

A future graph could link requirement → function → dependency → test → test
result. Parser-derived edges, LLM proposals, and executed evidence must remain
distinguishable; a later commit can make old evidence stale. This integration
does not claim to implement that graph or automatically select complete project
specifications from arbitrary conversation memories.

For ordinary memories, a factual-consistency checker needs a different contract:
what claim is being checked, whose statement it is, when it applies, which
sources count as evidence, and what remains unknown. Rephrasing an unsupported
claim as a requirement does not supply evidence for it. SUE could help review
that checker's specification, but would not itself become the fact checker.
