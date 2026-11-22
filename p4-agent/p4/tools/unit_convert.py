FACTORS_TO_CRORE = {
    "crore": 1.0, "inr crore": 1.0,
    "lakh": 0.01, "inr lakh": 0.01,
    "million": 0.1, "inr million": 0.1,
    "billion": 100.0, "inr billion": 100.0,
}
def unit_convert(value: float, from_unit: str, to_unit: str = "crore") -> dict:
    a, b = from_unit.strip().lower(), to_unit.strip().lower()
    if a not in FACTORS_TO_CRORE or b not in FACTORS_TO_CRORE:
        raise ValueError(f"Unsupported unit: {from_unit} or {to_unit}")
    result = float(value) * FACTORS_TO_CRORE[a] / FACTORS_TO_CRORE[b]
    return {"input_value": value, "from_unit": from_unit, "value": result, "to_unit": to_unit}
