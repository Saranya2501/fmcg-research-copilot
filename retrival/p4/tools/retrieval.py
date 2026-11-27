"""Adapter for P3 retrieval source (retrieve.py) described in INTEGRATION.md.

P3 public API:
    from retrieve import retrieve, get_table
    retrieve(query=..., k=..., filters=...)
    get_table(doc_id=..., page=..., section_hint=...)

The adapter also tolerates the earlier provisional source_id/table_id interface
for compatibility with the original P4 starter.
"""
from typing import Callable, Optional
import inspect

class RetrievalAdapter:
    def __init__(self, retrieve_fn: Optional[Callable] = None,
                 table_fn: Optional[Callable] = None):
        self.retrieve_fn = retrieve_fn
        self.table_fn = table_fn

    @classmethod
    def from_p3_path(cls, rag_path: str):
        """Import P3's retrieve.py from the supplied RAG project directory."""
        import sys
        from pathlib import Path
        path = str(Path(rag_path).expanduser().resolve())
        if path not in sys.path:
            sys.path.insert(0, path)
        from retrieve import retrieve, get_table
        return cls(retrieve_fn=retrieve, table_fn=get_table)

    def search_reports(self, query: str, k: int = 5, filters: dict | None = None) -> dict:
        if self.retrieve_fn is None:
            return {"status": "adapter_not_connected", "records": [],
                    "message": "P3 retrieve() has not been configured."}
        records = self.retrieve_fn(query=query, k=k, filters=filters or {})
        clean = []
        for record in records or []:
            item = dict(record)
            item["text_is_untrusted_data"] = True
            clean.append(item)
        return {"status": "ok" if clean else "not_found", "records": clean}

    def get_table(self, doc_id: str | None = None, page: int | None = None,
                  section_hint: str | None = None, source_id: str | None = None,
                  table_id: str | None = None) -> dict:
        if self.table_fn is None:
            return {"status": "adapter_not_connected", "tables": [],
                    "message": "P3 get_table() has not been configured."}
        resolved_doc_id = doc_id or source_id
        if not resolved_doc_id:
            return {"status": "invalid_arguments", "tables": [],
                    "message": "Pass doc_id from a retrieve() result."}
        params = inspect.signature(self.table_fn).parameters
        kwargs = {}
        if "doc_id" in params:
            kwargs["doc_id"] = resolved_doc_id
        elif "source_id" in params:
            kwargs["source_id"] = resolved_doc_id
        if "page" in params and page is not None:
            kwargs["page"] = page
        if "section_hint" in params and section_hint is not None:
            kwargs["section_hint"] = section_hint
        if "table_id" in params and table_id is not None:
            kwargs["table_id"] = table_id
        result = self.table_fn(**kwargs)
        if isinstance(result, dict):
            tables = [result]
        else:
            tables = result or []
        return {"status": "ok" if tables else "not_found", "tables": tables}
