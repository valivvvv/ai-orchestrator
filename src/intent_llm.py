"""
LLM baseline for intent classification (Task 3: L7).

The expensive counterpart to the TF-IDF classifier: ask Claude to label a query
as search / extract / summarize. Used by scripts/compare_intent.py to compare
latency, cost, and accuracy against the scikit-learn model.
"""
LABELS = ("search", "extract", "summarize")

CLASSIFY_PROMPT = """Clasifică intenția întrebării într-una din trei categorii:

- search: utilizatorul caută sau vrea să găsească/listeze documente (facturi, contracte, clienți, rapoarte).
- extract: utilizatorul vrea o valoare/câmp specific dintr-un document (CUI, IBAN, adresă, sumă, dată, contact).
- summarize: utilizatorul vrea un rezumat sau o sinteză a unui document sau set de documente.

Întrebare: {query}

Răspunde cu UN SINGUR cuvânt: search, extract sau summarize."""


def classify_intent_llm(llm, query: str) -> str:
    """Classify a query via the LLM; return one of LABELS.

    Parses the label out of the response (the prompt asks for a single word, but
    models sometimes add punctuation or a sentence). Falls back to "search" if no
    known label is found.
    """
    prompt = CLASSIFY_PROMPT.format(query=query)
    response = llm.generate_sync([{"role": "user", "content": prompt}]).lower()
    for label in LABELS:
        if label in response:
            return label
    return "search"
