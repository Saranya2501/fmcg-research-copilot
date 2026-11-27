from p4.config import METRIC_SYNONYMS

def metric_lookup(metric: str) -> dict:
    key = metric.strip().lower()
    for canonical, synonyms in METRIC_SYNONYMS.items():
        if key == canonical or key in [s.lower() for s in synonyms]:
            return {"status": "matched", "canonical": canonical, "synonyms": synonyms}
    return {"status": "unmapped", "input": metric, "clarification_needed": True}
