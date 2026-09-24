# SUE, requirements, and Castle memory

SUE analyzes software specifications and the consequences of interpreting their
requirements. It does **not** independently establish factual truth, inspect a
running application, or validate every record in a memory palace. Cognitive
Castle does not currently integrate SUE into ingestion or retrieval.

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

## A future Castle-to-SUE adapter: proposal, not implemented

For requirements stored in Castle, an adapter could:

1. Select an explicitly scoped project specification and revision for a stated
   decision, such as implementing a particular behavior. Preserve examples,
   exceptions, and definitions needed to interpret it.
2. Export the selected original passages unchanged into a frozen specification
   bundle. Record drawer IDs, source files/spans, revision timestamps, and hashes
   in a provenance manifest. Keep historical or superseded passages labeled;
   never silently convert conversation into new requirements.
3. Run SUE on that bundle with an explicit provider/model, call budget, and
   isolated context. Choosing Codex for a public README is not blanket permission
   to send private palace contents to an external provider.
4. Store findings as separate derived records linked to their exact sources,
   preserving run identity and disagreements. Do not rewrite source drawers or
   mark a finding as fact solely because the model produced it.
5. Verify proposed consequences separately against code and executed tests at a
   recorded commit. A graph could link requirement → function → dependency →
   test → test result. Parser-derived edges, LLM proposals, and executed evidence
   must remain distinguishable; a later commit can make old evidence stale.

For ordinary memories, a factual-consistency checker needs a different contract:
what claim is being checked, whose statement it is, when it applies, which
sources count as evidence, and what remains unknown. Rephrasing an unsupported
claim as a requirement does not supply evidence for it. SUE could help review
that checker's specification, but would not itself become the fact checker.
