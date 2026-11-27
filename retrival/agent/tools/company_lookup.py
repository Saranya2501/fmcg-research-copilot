from agent.config import COMPANIES, UNLISTED_OR_UNSUPPORTED

def company_lookup(name: str) -> dict:
    key = name.strip().lower()
    if key in UNLISTED_OR_UNSUPPORTED:
        return {"status": "unsupported", "input": name,
                "reason": "Company is outside the approved listed-company scope."}
    for item in COMPANIES.values():
        names = [item["canonical"].lower()] + [x.lower() for x in item["aliases"]]
        if key in names:
            result = {"status": "supported", "input": name,
                      "canonical": item["canonical"], "aliases": item["aliases"]}
            if item.get("segment_note"):
                result["scope_note"] = item["segment_note"]
            return result
    return {"status": "unknown", "input": name,
            "reason": "Not found in the current ten-company registry; confirm with P1 before proceeding."}
