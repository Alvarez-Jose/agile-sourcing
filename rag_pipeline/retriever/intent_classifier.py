"""
rag_pipeline/retriever/intent_classifier.py
Classifies user questions into procurement intent categories.
Replaces the hardcoded keyword overrides in rewrite_query().
"""

import json
import pickle
from pathlib import Path
from typing import Optional

from sentence_transformers import SentenceTransformer

EMBED_MODEL = "all-MiniLM-L6-v2"
DEFAULT_MODEL_DIR = Path("models/intent_classifier")

# Maps intent label -> search keywords that retrieve the right policy chunks
INTENT_TO_KEYWORDS = {
    "competitive_bidding": "competitive bidding threshold sole source justification BUS-43 procurement",
    "equipment_management": "inventorial equipment property tag threshold BUS-29 equipment management",
    "federal_funds": "federal funds NIH grant SSPR form federal checklist compliance funding source",
    "conflict_of_interest": "conflict of interest post-employment restrictions gifts disclosure COI",
    "contracts_services": "independent contractor consulting services agreement worker classification",
    "general_policy": None,  # fall through to LLM keyword rewrite
}


class IntentClassifier:
    def __init__(self, model_dir: Path = DEFAULT_MODEL_DIR):
        self._embedder: Optional[SentenceTransformer] = None
        self._clf = None
        self._labels: Optional[list] = None
        self.model_dir = Path(model_dir)
        self._loaded = False

    def _load(self):
        """Lazy-load model on first use."""
        clf_path = self.model_dir / "classifier.pkl"
        labels_path = self.model_dir / "labels.json"

        if not clf_path.exists():
            return False

        self._embedder = SentenceTransformer(EMBED_MODEL)
        with open(clf_path, "rb") as f:
            self._clf = pickle.load(f)
        with open(labels_path) as f:
            self._labels = json.load(f)

        self._loaded = True
        return True

    def predict(self, question: str) -> tuple[str, float]:
        """
        Returns (intent_label, confidence).
        Falls back to ('general_policy', 0.0) if model not trained yet.
        """
        if not self._loaded:
            if not self._load():
                return "general_policy", 0.0

        vec = self._embedder.encode([question])
        proba = self._clf.predict_proba(vec)[0]
        idx = proba.argmax()
        label = self._clf.classes_[idx]
        confidence = float(proba[idx])
        return label, confidence

    def get_search_keywords(self, question: str) -> Optional[str]:
        """
        Returns search keywords for the detected intent, or None if the
        classifier is not trained or confidence is too low (caller falls
        through to LLM keyword rewrite).
        """
        intent, confidence = self.predict(question)

        if confidence < 0.5:
            return None

        return INTENT_TO_KEYWORDS.get(intent)


# Module-level singleton — loaded once per process
_classifier = IntentClassifier()


def classify_intent(question: str) -> tuple[str, float]:
    return _classifier.predict(question)


def get_search_keywords(question: str) -> Optional[str]:
    return _classifier.get_search_keywords(question)
