# ⚠️ ARCHIVED — small-corpus exploratory Phase-2 runs (superseded)

These five stage docs (`01-hybrid` … `05-crag`) recorded an **early, stage-by-stage** exploration
of the advanced-RAG features on a **small corpus** (≈19 docs / 42-pair golden set). Those numbers
are **not legitimate** as headline results — the corpus was too small to show the real effect of
the Phase-2 stages, and the per-stage DROP/KEEP verdicts were drawn from that small sample.

They are kept **only** for the engineering rationale they captured (why each stage exists, how it
was wired, what to watch), which informed the decisions for the real run:
- run **all stages on at once** (Option A) rather than one-at-a-time,
- use **rerank candidate k ≈ 10** (not 60) for latency/cost,
- add the **FI-3 per-chunk metadata filter** as the structural fix for FI-5.

**The canonical Phase-2 record is the head-to-head against the `phase1-final` baseline** on the
full **30-doc / 534-chunk** corpus with the **61-pair** golden set — see `../PHASE-2-CONCLUSION.md`
and `../README.md`. Do not cite any number from this folder as a result.
