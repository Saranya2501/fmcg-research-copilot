from agent.tools.calculator import calculator
from agent.tools.unit_convert import unit_convert
from agent.tools.company_lookup import company_lookup
from agent.tools.metric_lookup import metric_lookup
from agent.tools.retrieval import RetrievalAdapter
from agent.tools.report import generate_report

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
