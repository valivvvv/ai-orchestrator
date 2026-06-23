"""
Intent classifier (Task 3: L7).

Lazy-loads the TF-IDF + LogisticRegression model trained by
scripts/train_intent.py and classifies a query into search / extract / summarize.
"""
from pathlib import Path

import joblib

MODEL_PATH = Path(__file__).parent.parent / "data" / "intent" / "intent_classifier.joblib"

_pipeline = None


def _load_pipeline():
    """Load the persisted pipeline once, on first use."""
    global _pipeline
    if _pipeline is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Model not found at {MODEL_PATH}. Run: python scripts/train_intent.py"
            )
        _pipeline = joblib.load(MODEL_PATH)
    return _pipeline


def detect_intent(query: str) -> tuple[str, float]:
    """Return the predicted label and its confidence (max class probability)."""
    pipeline = _load_pipeline()
    label = pipeline.predict([query])[0]
    confidence = max(pipeline.predict_proba([query])[0])
    return str(label), float(confidence)
