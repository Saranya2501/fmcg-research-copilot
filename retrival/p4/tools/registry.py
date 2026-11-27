from p4.tools.calculator import calculator
from p4.tools.unit_convert import unit_convert
from p4.tools.company_lookup import company_lookup
from p4.tools.metric_lookup import metric_lookup
from p4.tools.retrieval import RetrievalAdapter
from p4.tools.report import generate_report

def build_tool_registry(retrieval: RetrievalAdapter):
    return {
        "search_reports": retrieval.search_reports,
        "get_table": retrieval.get_table,
        "calculator": calculator,
        "unit_convert": unit_convert,
        "company_lookup": company_lookup,
        "metric_lookup": metric_lookup,
        "generate_report": generate_report,
    }
