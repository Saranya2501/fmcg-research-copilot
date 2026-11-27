import pytest
from agent.tools.calculator import calculator
from agent.tools.unit_convert import unit_convert
from agent.tools.company_lookup import company_lookup
from agent.tools.metric_lookup import metric_lookup
from agent.tools.retrieval import RetrievalAdapter
from agent.tools.registry import build_tool_registry
from agent.tools.report import generate_report
from agent.guards import gatekeeper, detect_repeated_call, enforce_step_limit, enforce_repair_limit
from agent.schemas.models import CopilotResponse, Plan

def test_calculator_and_block_unsafe_expression():
    assert calculator("(100 + 50) / 2")["value"] == 75
    with pytest.raises((ValueError, SyntaxError)):
        calculator("__import__('os').system('id')")

def test_currency_scale_conversion():
    assert unit_convert(100, "lakh", "crore")["value"] == 1
    assert unit_convert(10, "million", "crore")["value"] == 1
    assert unit_convert(1, "billion", "crore")["value"] == 100

def test_ten_company_registry_and_itc_segment_note():
    assert company_lookup("HUL")["canonical"] == "Hindustan Unilever"
    assert company_lookup("Colgate India")["status"] == "supported"
    assert company_lookup("Amul")["status"] == "unsupported"
    assert "FMCG segment" in company_lookup("ITC")["scope_note"]

def test_metric_synonyms():
    assert metric_lookup("A&P")["status"] == "matched"
    assert metric_lookup("net sales")["canonical"] == "revenue from operations"

def test_refusal_codes_separated():
    assert gatekeeper("Should I buy Nestle shares?")["refusal_code"] == "prohibited_investment_advice"
    assert gatekeeper("Forecast Dabur revenue next year")["refusal_code"] == "prohibited_forecast"
    assert gatekeeper("Give me a target price for ITC")["refusal_code"] == "prohibited_valuation"
    assert gatekeeper("Analyze Patanjali revenue")["refusal_code"] == "unsupported_unlisted_company"
    assert gatekeeper("What was Dabur revenue in FY24?")["status"] == "allowed"

def test_limits_and_loop_detection():
    assert detect_repeated_call([("calculator", "1+1"), ("calculator", "1+1")])
    enforce_step_limit(10)
    with pytest.raises(RuntimeError): enforce_step_limit(11)
    enforce_repair_limit(2)
    with pytest.raises(RuntimeError): enforce_repair_limit(3)

def test_retrieval_adapter_passthrough_and_untrusted_flag():
    adapter = RetrievalAdapter(retrieve_fn=lambda **kw: [
        {"source_id":"DABUR-AR24","company":"Dabur India","document":"Annual Report FY24","page":142,"text":"evidence"}
    ])
    result = adapter.search_reports("revenue", 5, {"company":"Dabur India"})
    assert result["status"] == "ok"
    assert result["records"][0]["page"] == 142
    assert result["records"][0]["text_is_untrusted_data"] is True

def test_retrieval_adapter_pending_state():
    assert RetrievalAdapter().search_reports("sales")["status"] == "adapter_not_connected"

def test_seven_tool_registry():
    tools = build_tool_registry(RetrievalAdapter())
    assert set(tools) == {"search_reports","get_table","calculator","unit_convert",
                          "company_lookup","metric_lookup","generate_report"}

def test_report_export_approval_gate(tmp_path):
    blocked = generate_report("Test", [], approved=False, output_path=str(tmp_path/"no.docx"))
    assert blocked["status"] == "approval_required"
    assert not (tmp_path/"no.docx").exists()
    allowed = generate_report("Test", [], approved=True, output_path=str(tmp_path/"yes.docx"))
    assert allowed["status"] == "exported"
    assert (tmp_path/"yes.docx").exists()

def test_p1_response_schema():
    valid = CopilotResponse(status="partial", answer="Evidence missing").model_dump()
    assert valid["status"] == "partial"
    with pytest.raises(Exception):
        CopilotResponse(status="success", answer="invalid")

def test_planner_schema_supports_subtasks():
    plan = Plan.model_validate({"use_case":"UC1","subtasks":[{"task_id":"T1","objective":"Find FY24 revenue"}]})
    assert plan.subtasks[0].task_id == "T1"
