# Competitive Research Copilot — P4 Agent & Tools

P4 package for the team project. See the
[P3 integration notes](integration/P3_LIVE_INTEGRATION_STATUS.md) for retrieval
assets and the [P5 guide](../p5-deployment/README.md) for the full application.

## Verified local baseline

On 26 November 2026, the P4 and integration suite passed 20 tests locally.
These are offline checks, not evidence of a live end-to-end IITK run.

## Offline setup and checks

From the repository root (for the full app, install P5 dependencies instead):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r p4-agent/requirements.txt
PYTHONPATH=p4-agent python -m pytest p4-agent/tests p4-agent/integration/tests -q
```

## P2/P3 research path
The Streamlit app calls `integration/runtime.py::run_query` through P5's adapter.
P2 source and prompts are included in `integration/p2_agents/`; retrieval source
is included in `p3_retrieval/`. Download the indexes and full parsed corpus using
the [integration notes](integration/P3_LIVE_INTEGRATION_STATUS.md), and configure
the LLM using the [IITK instructions](../p5-deployment/README.md#iitk-institute-api).

The separate LangGraph workflow in `p4/graph.py` and its tool registry are included
in the repository. Streamlit uses the single-answer integration runner; brief
export and the graph's critic revision loop are not exposed through that app.

No secrets, tokens or private credentials are included. Keep `.env` untracked.


## Notebook scope

The tracked [P3 notebook](../p3-retrieval/colab_test.ipynb) is a standalone
retrieval exercise. It does not launch the complete Streamlit agent application.
