"""
Smoke test for Anthropic prompt caching (Phase 2).

Runs ONE Orchestrator.run with a known-retrieving query so the LLM is actually
called (a no-results query short-circuits node_evaluate/node_answer and sends no
system block). The static orchestrator_system.yaml prompt is attached as a cached
system block; the first system-block call writes it to cache (cache_creation), a
later call in the same run reads it back (cache_read).

Measurement is done WITHIN the single run via llm.usage_log, not at run
boundaries: cache_creation fires exactly once (the first system-block call,
node_evaluate) and is never the final generate_sync of the run, so only the
accumulated log can observe both creation and read. A lightweight wrapper around
generate_sync records per-call latency, index-aligned with usage_log (every call
appends exactly one usage record).

Usage:
    python scripts/smoke_prompt_cache.py
"""
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skillab-py" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from skillab import get_llm
from orchestrator import Orchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)

# Haiku 4.5 pricing (verified via claude-api skill 2026-06-23): $1.00 / 1M input
# tokens; cache reads bill ~0.1x of the input rate.
INPUT_PRICE_PER_TOKEN = 1.00 / 1_000_000
CACHE_READ_MULTIPLIER = 0.1

QUERY = "Ce contact are DataPro?"  # known-retrieving -> LLM is actually called


def main() -> None:
    # Fresh instance so cache_system=True does not poison the shared cached
    # provider used by other agents (pitfall #8).
    llm = get_llm("anthropic", cached=False)
    llm.cache_system = True
    print(f"Using LLM: anthropic / {llm.model} (cache_system={llm.cache_system})")

    orchestrator = Orchestrator(llm=llm)

    # Record per-call latency, index-aligned with usage_log.
    timings: list[float] = []
    inner = llm.generate_sync

    def timed(messages):
        start = time.perf_counter()
        result = inner(messages)
        timings.append(time.perf_counter() - start)
        return result

    llm.generate_sync = timed

    llm.reset_usage()
    print("\n" + "=" * 70)
    print(f"RUN  query={QUERY!r}")
    print("=" * 70)
    result = orchestrator.run(QUERY)
    print(f"Status: {result['status']}")
    print(f"Answer: {result['answer'][:200]}")

    log = llm.usage_log
    print("\n" + "=" * 70)
    print("usage_log (one entry per generate_sync call, in order)")
    print("=" * 70)
    print(f"{'#':>2}  {'input':>6}  {'cache_create':>12}  {'cache_read':>10}  {'output':>6}  {'latency_s':>9}")
    for index, usage in enumerate(log):
        creation = usage.get("cache_creation_input_tokens") or 0
        read = usage.get("cache_read_input_tokens") or 0
        latency = timings[index] if index < len(timings) else float("nan")
        print(
            f"{index:>2}  {usage['input_tokens']:>6}  {creation:>12}  "
            f"{read:>10}  {usage['output_tokens']:>6}  {latency:>9.2f}"
        )

    # Locate the creation entry and a LATER read entry.
    creation_index = next(
        (i for i, u in enumerate(log) if (u.get("cache_creation_input_tokens") or 0) > 0),
        None,
    )
    read_index = next(
        (
            i
            for i, u in enumerate(log)
            if creation_index is not None
            and i > creation_index
            and (u.get("cache_read_input_tokens") or 0) > 0
        ),
        None,
    )

    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)
    assert creation_index is not None, (
        "No cache_creation > 0 found - system block under the min cacheable "
        "tokens (4096 for Haiku 4.5) or caching not attached."
    )
    assert read_index is not None, (
        "No later cache_read > 0 found - the cached block was not reused "
        "(TTL lapsed or only one system-block call happened)."
    )
    print(f"cache_creation at call #{creation_index}  (node_evaluate, first system block)")
    print(f"cache_read     at call #{read_index}  (a later system-block call, e.g. node_answer)")

    cached_tokens = log[read_index].get("cache_read_input_tokens") or 0
    full_cost = cached_tokens * INPUT_PRICE_PER_TOKEN
    cached_cost = cached_tokens * INPUT_PRICE_PER_TOKEN * CACHE_READ_MULTIPLIER
    print(
        f"\nTokens served from cache on the read call: {cached_tokens}"
        f"\n  full input price:   ${full_cost:.6f}"
        f"\n  cached read price:  ${cached_cost:.6f}  (~{CACHE_READ_MULTIPLIER:.0%})"
        f"\n  saved per read:     ${full_cost - cached_cost:.6f}"
    )

    creation_latency = timings[creation_index]
    read_latency = timings[read_index]
    print(
        f"\nLatency  creation call: {creation_latency:.2f}s"
        f"  |  read call: {read_latency:.2f}s"
        f"  |  delta: {creation_latency - read_latency:+.2f}s"
    )


if __name__ == "__main__":
    main()
