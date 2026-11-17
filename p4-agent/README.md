# P4 — Agent & Tools

Owner: Rohit

Owns the LangGraph agent graph, 7 tool definitions (including `search_reports` and `get_table` which call P3's `retrieve()` and `get_table()`), state management, and agent guards.

## Integrating with P3 retrieval

See `p3-retrieval/INTEGRATION.md` for the full interface contract.

```python
import sys
sys.path.insert(0, "../p3-retrieval")
from retrieve import retrieve, get_table
```

Index files are in the shared Drive folder — place at `p3-retrieval/index/` before running.
