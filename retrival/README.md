# Competitive Research Copilot — P4 Agent & Tools

The research runner combines the prompting agents in `integration/p2_agents/` with the retrieval code in `core/`. For credentials, research data, and launch commands, follow the [project quick start](../README.md#run-the-agent).

## Developer checks

From this directory, with the project virtual environment active, run:

```bash
python -m pip install -r requirements.txt
PYTHONPATH=. python -m pytest -q tests integration/tests
```

## Google Colab
Upload `colab/Competitive_Research_Copilot_P4_Ready_to_Run.ipynb` to Colab and run cells from top to bottom. It automatically detects the project root after ZIP extraction.
