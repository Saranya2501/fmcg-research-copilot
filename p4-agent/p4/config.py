MAX_STEPS_PER_SUBTASK = 10
MAX_REPAIR_ROUNDS = 2
DEFAULT_TOKEN_BUDGET = 6000
RETRIEVAL_TOP_K = 5
TOOL_TIMEOUT_SECONDS = 45

# Ten-company starter registry. P1 must confirm final aliases and listing scope.
COMPANIES = {
    "hul": {"canonical": "Hindustan Unilever", "aliases": ["HUL", "Hindustan Unilever"]},
    "itc": {"canonical": "ITC", "aliases": ["ITC"], "segment_note": "Use the FMCG segment for FMCG-specific comparisons; do not treat total ITC as FMCG-only."},
    "nestle india": {"canonical": "Nestlé India", "aliases": ["Nestle India", "Nestlé India"]},
    "dabur": {"canonical": "Dabur India", "aliases": ["Dabur"]},
    "britannia": {"canonical": "Britannia Industries", "aliases": ["Britannia"]},
    "marico": {"canonical": "Marico", "aliases": ["Marico"]},
    "godrej consumer": {"canonical": "Godrej Consumer Products", "aliases": ["GCPL", "Godrej Consumer", "Godrej Consumer Products"]},
    "colgate": {"canonical": "Colgate-Palmolive (India)", "aliases": ["Colgate India", "Colgate-Palmolive India"]},
    "tata consumer": {"canonical": "Tata Consumer Products", "aliases": ["Tata Consumer", "Tata Consumer Products"]},
    "emami": {"canonical": "Emami", "aliases": ["Emami"]},
}
UNLISTED_OR_UNSUPPORTED = {"amul", "patanjali"}
PROHIBITED_PATTERNS = {
    "prohibited_investment_advice": [
        "should i buy", "should i sell", "should i hold", "buy this stock",
        "sell this stock", "hold or sell", "which stock should i invest",
        "should i invest in"
    ],
    "prohibited_forecast": [
        "forecast", "predict next year", "future revenue", "future share price",
        "expected share price", "projected earnings", "predict market share",
        "what will revenue be", "how much will it grow"
    ],
    "prohibited_valuation": [
        "target price", "price target", "intrinsic value", "fair value",
        "valuation", "overvalued", "undervalued"
    ],
}
METRIC_SYNONYMS = {
    "a&p": ["advertisement and sales promotion", "advertising and publicity"],
    "advertisement and sales promotion": ["a&p"],
    "revenue from operations": ["revenue", "net sales"],
    "revenue": ["revenue from operations", "net sales"],
    "ebitda margin": ["ebitda / revenue from operations"],
}
