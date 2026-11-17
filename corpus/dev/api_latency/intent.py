# Model-drafted 2026-11-16; reviewed by Rich 2026-11-16 (PROVENANCE.md).
"""Checks for api_latency: one per bullet in the prompt.

Every number in the data is whole, so "comma separators" doesn't fix the decimals. A
highlighted row needn't include its stub cell: truth.py fills it, but every trial so far
(all arms) fills only the body, which reads as a highlighted row too.
"""

from harness.score.intent import number


def check(t, truth):
    def col(name):
        return t.col(name, like=truth.col(name))

    t.formatted([col("avg_ms"), col("p95_ms"), col("p99_ms")], number())
    t.formatted(col("requests"), number())
    t.formatted(col("errors"), number())
    t.filled(col("p99_ms").num > 1000, color="red", light=True, stub=False)
    t.title("API Performance Dashboard")
    t.order(col("p99_ms"), descending=True)
    t.stub(col("endpoint"))
