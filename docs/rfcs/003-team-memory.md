# RFC 003 — Team Memory (multi-user palaces)

**Status:** Draft — exploration only, no implementation commitment
**Date:** 2026-07-26
**Author:** Ladislav Bihari (drafted with Claude)

## Problem

Castle is fundamentally a single-person palace. Zep and mem0 are built
for production multi-tenant use; teams that want shared AI memory today
cannot choose Castle. This RFC maps the honest option space so the
decision — including "never" — is deliberate rather than default.

## Constraints that any design must survive

These are Castle's non-negotiables (CLAUDE.md), restated as they apply
to multi-user:

1. **Verbatim always** — shared memory still stores exact words. No
   summarize-for-sharing tier.
2. **Local-first, privacy by architecture** — "your data never leaves
   your machine" must become "your data never leaves machines you
   chose". No Castle-operated cloud. Ever.
3. **Entity-first** — people are already first-class (wings). A team
   palace makes *colleagues* entities, which raises consent questions
   single-user Castle never had: my notes about you, in a store you
   can read.
4. **Performance budgets** — hooks < 500 ms even when a sync layer
   exists; sync must be background, never blocking filing or search.

## Option space

### Option A — Shared palace on shared storage (lowest tech, available today)

A palace directory on a network filesystem / synced folder (Syncthing,
NFS, git-LFS-style), every member's `castle-mcp` pointed at it.

- Works now with zero code. LanceDB file locks serialize writers.
- Fails at scale: lock contention across machines over network FS is
  fragile; conflicting concurrent writes can corrupt; no per-member
  access control at all — everyone reads everything.
- Verdict: document as an "at your own risk" pattern for 2–3-person
  trusted teams; never call it supported.

### Option B — Wing-level federation (pull-based, no server)

Each member keeps their own palace. A wing can be *published* (exported
as an append-only log of drawers) and *subscribed* (mirrored read-only
into a teammate's palace under `wing_<name>@<person>`). Sync = fetching
a file over whatever transport the team already trusts (git repo, S3
bucket they own, Syncthing).

- Preserves every constraint: local-first (you host your own export),
  consent-explicit (publishing a wing is a deliberate act, per wing),
  verbatim, no server.
- Search spans local + subscribed wings transparently; provenance
  (`added_by`, origin palace) already exists in metadata.
- Cost: export/import format, dedup on re-import (drawer IDs are
  already content-addressed — hash of source+chunk — which helps),
  staleness semantics (subscriber lag is a feature, not a bug).
- This is the design that feels most Castle-shaped.

### Option C — Palace server (multi-tenant daemon)

A `castle-serve` process owning one palace, multiple clients over
MCP-over-HTTP with per-user auth and per-wing ACLs.

- This is the Zep/mem0 shape. It abandons local-first for the server
  operator's machine being "the" machine, adds auth/ACL surface Castle
  has never carried, and turns a filesystem tool into an ops artifact.
- Verdict: out of character. If a team wants this shape, Zep is the
  honest recommendation — Castle should not become a worse Zep.

## Recommendation

**B, eventually; A, documented with warnings, now; C, never.**

Sequencing gate: B should not start before (1) PyPI publishing is live
(issue #87 — adoption first), and (2) the info-aware-filing benchmark
gate has resolved (retrieval quality work in flight). Team memory is a
multi-month commitment; starting it while single-user fundamentals are
still moving would be scope-thrash.

## Open questions for the eventual B design

- Export format: JSONL of (drawer_id, content, metadata) per wing?
  Signed? Compressed?
- Subscribed-wing novelty: are a teammate's drawers "priors" for my
  info-aware filing? (Probably yes within the mirrored wing, no
  across.)
- Revocation: unpublishing a wing cannot un-send data already fetched —
  document as unrecoverable, like any shared file.
- Does the knowledge graph federate, or stay strictly local? (Lean:
  strictly local; mirrored drawers feed the local KG like any content.)

## Non-goals confirmed

No Castle cloud. No accounts. No telemetry. No summarized "shared
digest" tier — verbatim or nothing.
