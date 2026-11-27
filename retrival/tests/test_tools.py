from agent.tools.calculator import calculator
from agent.tools.unit_convert import unit_convert
from agent.tools.company_lookup import company_lookup
from agent.tools.metric_lookup import metric_lookup
from agent.guards import gatekeeper, detect_repeated_call
import pytest

def test_calculator():
    assert calculator("(100 + 50) / 2")["value"] == 75
    with pytest.raises(ValueError): calculator("__import__('os').system('id')")

def test_unit_convert():
    assert unit_convert(100, "lakh", "crore")["value"] == 1
    assert unit_convert(1, "billion", "crore")["value"] == 100

def test_company_alias():
    assert company_lookup("HUL")["canonical"] == "Hindustan Unilever"
    assert company_lookup("Amul")["status"] == "unsupported"

def test_metric_synonym():
    assert metric_lookup("A&P")["status"] == "matched"

def test_refusal_gate():
    assert gatekeeper("Should I buy Nestle shares?")["status"] == "refused"
    assert gatekeeper("What was Dabur revenue in FY24?")["status"] == "allowed"

def test_loop_detection():
    assert detect_repeated_call([("calculator", "1+1"), ("calculator", "1+1")])
