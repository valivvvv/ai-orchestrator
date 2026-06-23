"""
Compare the scikit-learn intent classifier against an LLM baseline (Task 3: L7).

Over the held-out test_data.json, runs both classifiers and prints a table of
latency (avg ms/call), cost (LLM tokens x price vs ~$0), and accuracy (fraction
matching the ground-truth label). This is the Task 3 deliverable.

Usage:
    python scripts/compare_intent.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skillab-py" / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from skillab import get_llm
from intent_classifier import detect_intent
from intent_llm import classify_intent_llm

TEST_PATH = Path(__file__).parent.parent / "data" / "intent" / "test_data.json"

# Haiku 4.5 pricing (verified via claude-api skill 2026-06-23): $1.00 / 1M input,
# $5.00 / 1M output.
INPUT_PRICE_PER_TOKEN = 1.00 / 1_000_000
OUTPUT_PRICE_PER_TOKEN = 5.00 / 1_000_000


def main() -> None:
    examples = json.loads(TEST_PATH.read_text(encoding="utf-8"))
    texts = [item["text"] for item in examples]
    labels = [item["label"] for item in examples]
    print(f"Loaded {len(texts)} held-out test examples from {TEST_PATH.name}\n")

    # --- scikit-learn classifier ---
    # Warm up so the one-time joblib load is not charged to per-call latency.
    detect_intent(texts[0])
    sklearn_correct = 0
    sklearn_latencies: list[float] = []
    for text, true_label in zip(texts, labels):
        start = time.perf_counter()
        label, _confidence = detect_intent(text)
        sklearn_latencies.append(time.perf_counter() - start)
        sklearn_correct += int(label == true_label)

    # --- LLM baseline ---
    llm = get_llm("anthropic", cached=False)
    llm.reset_usage()
    llm_correct = 0
    llm_latencies: list[float] = []
    for text, true_label in zip(texts, labels):
        start = time.perf_counter()
        label = classify_intent_llm(llm, text)
        llm_latencies.append(time.perf_counter() - start)
        llm_correct += int(label == true_label)

    total = len(texts)
    sklearn_avg_ms = 1000 * sum(sklearn_latencies) / total
    llm_avg_ms = 1000 * sum(llm_latencies) / total

    # LLM cost from accumulated usage; classifier cost is effectively $0.
    input_tokens = sum(usage["input_tokens"] for usage in llm.usage_log)
    output_tokens = sum(usage["output_tokens"] for usage in llm.usage_log)
    llm_cost = input_tokens * INPUT_PRICE_PER_TOKEN + output_tokens * OUTPUT_PRICE_PER_TOKEN

    sklearn_accuracy = sklearn_correct / total
    llm_accuracy = llm_correct / total

    print("=" * 66)
    print(f"{'classifier':<14}  {'accuracy':>10}  {'avg latency':>13}  {'total cost':>12}")
    print("-" * 66)
    print(f"{'scikit-learn':<14}  {sklearn_accuracy:>9.1%}  {sklearn_avg_ms:>10.2f} ms  {'$0.000000':>12}")
    print(f"{'LLM (Claude)':<14}  {llm_accuracy:>9.1%}  {llm_avg_ms:>10.2f} ms  {'$' + format(llm_cost, '.6f'):>12}")
    print("=" * 66)

    speedup = llm_avg_ms / sklearn_avg_ms if sklearn_avg_ms else float("inf")
    print(
        f"\nscikit-learn is ~{speedup:.0f}x faster and ~free "
        f"(LLM: {input_tokens} input + {output_tokens} output tokens over {total} calls)."
    )


if __name__ == "__main__":
    main()
