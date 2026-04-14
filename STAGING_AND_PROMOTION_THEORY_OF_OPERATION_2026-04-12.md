# Staging And Promotion Theory Of Operation 2026-04-12

## Purpose

This document explains how CorpusForge fits into the proactive quality process for future network-drive additions. The goal is to make dirty upstream data fail in staging before it contaminates the downstream HybridRAG_V2 production store.

## Repo Role

CorpusForge is the authoritative upstream export system.

Its job is to:

- ingest and normalize source data
- create deterministic export artifacts
- expose enough metadata and integrity signals for downstream quality gates

It should not assume that all exported identifiers are business-safe for downstream entity extraction.

## Findings

Recent work showed:

- export integrity checks are now formalized
- the Forge-to-V2 metadata contract is clearer than before
- but clean export integrity is not the same thing as clean business-entity semantics

In other words:

- Forge can produce a structurally valid export
- V2 still needs a promotion gate before business entities from new deltas become authoritative

## Lessons Learned

1. Structural integrity and semantic integrity are different problems.
2. A valid export can still carry text that produces dirty Tier 1 entities downstream.
3. Network-drive additions must be treated as staged deltas, not automatic production truth.
4. The promotion decision belongs after export integrity checks and before authoritative store merge.

## Path Forward

The future production flow should be:

1. New network-drive data enters Forge staging.
2. Forge produces a deterministic export with integrity checks.
3. HybridRAG_V2 imports the staged export into a non-authoritative staging store.
4. Tier 1 regex gates and confusion audits run on that staged delta.
5. Only a passing delta is promoted into the authoritative downstream store.

This means:

- Forge remains the authoritative export repo
- V2 owns the business-entity promotion gate
- production promotion becomes explicit, not accidental

## Technical Theory Of Operation

The cross-repo promotion model should be:

1. Forge export integrity gate
2. V2 import into staging
3. Tier 1 preflight gate
4. delta confusion audit
5. shadow extraction approval
6. authoritative promotion

Forge should continue providing:

- consistent manifests
- chunk/vector/artifact integrity
- metadata that supports downstream routing and provenance

V2 should continue owning:

- business-entity extraction quality
- fail-closed promotion logic
- downstream retrieval and answer trust

## Non-Technical Theory Of Operation

Plain-English version:

- Forge packages the data cleanly
- V2 decides whether the data is safe to trust as business knowledge
- nothing new should go straight from the network drive into the production answer system without passing staged checks

## Manager Status Summary

If asked why the process is taking time, the short answer is:

"We are turning the pipeline into a staged promotion system instead of a one-step ingest system. Forge now gives us stronger integrity signals, and V2 is being hardened so new data additions are audited before they become production truth. This avoids repeated retroactive cleanup when dirty identifiers sneak in from future network-drive deltas."

## Definition Of Done For This Cross-Repo Phase

This phase is complete when:

- Forge exports remain deterministic and integrity-checked
- V2 rejects dirty staged deltas automatically
- only passing deltas are promoted into the authoritative store
- future network-drive additions no longer require retroactive cleanup as the normal operating mode

