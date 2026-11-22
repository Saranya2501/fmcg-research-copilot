# Competitive Research Copilot — P4 Agent & Tools

P4 package for the team project. See `INTEGRATION_STATUS.md` and `GROUP_REQUEST.md` for current readiness and dependencies.

## Verified local baseline (before refresh)
- 18 P4 tests passed on the user's Mac environment previously; this package refresh has 20 tests passing in the current verification environment.
- Imports, 7-tool registry and LangGraph compile smoke tests passed.

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. python -m pytest -v
# Or run the combined suite: python -m pytest -q
```

## P2/P3 research path
See `integration/runtime.py`. It needs teammate P2 and P3 source directories and a configured LLM client. It is not yet a validated live end-to-end run.

No secrets, tokens or private credentials are included. Keep `.env` untracked.


## Google Colab
Upload `colab/Competitive_Research_Copilot_P4_Ready_to_Run.ipynb` to Colab and run cells from top to bottom. It automatically detects the project root after ZIP extraction.
