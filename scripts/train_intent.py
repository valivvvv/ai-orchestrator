"""
Train the intent classifier (Task 3: L7).

TF-IDF (1-2 grams) + LogisticRegression over training_data.json, persisted with
joblib. Labels: search / extract / summarize.

Usage:
    python scripts/train_intent.py
"""
import json
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.pipeline import Pipeline

DATA_DIR = Path(__file__).parent.parent / "data" / "intent"
TRAINING_PATH = DATA_DIR / "training_data.json"
MODEL_PATH = DATA_DIR / "intent_classifier.joblib"


def main() -> None:
    examples = json.loads(TRAINING_PATH.read_text(encoding="utf-8"))
    texts = [item["text"] for item in examples]
    labels = [item["label"] for item in examples]
    print(f"Loaded {len(texts)} training examples from {TRAINING_PATH.name}")

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2))),
        ("clf", LogisticRegression(max_iter=1000)),
    ])
    pipeline.fit(texts, labels)

    train_accuracy = accuracy_score(labels, pipeline.predict(texts))
    print(f"Train accuracy: {train_accuracy:.3f}")

    joblib.dump(pipeline, MODEL_PATH)
    print(f"Saved model -> {MODEL_PATH}")


if __name__ == "__main__":
    main()
