"""Entity extraction — stage 8 of the Forge pipeline.

Optional stage. When enabled, GLiNER (zero-shot NER) runs across every
chunk and produces candidate entities (part numbers, people, sites,
dates, organizations, failure modes, actions) with confidence scores.
Those candidates are written to ``entities.jsonl`` in the export and
V2 uses them to seed its knowledge graph.

Runs on CPU by default. For dense corpora this can be the slow step,
so operators usually turn it on only when V2 needs entity coverage.
"""
