FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    RAG_RERANKER_ENABLED=false

WORKDIR /app

COPY p5-deployment/requirements.txt /app/p5-deployment/requirements.txt
COPY p5-deployment/requirements-local-models.txt /app/p5-deployment/requirements-local-models.txt
ARG INSTALL_LOCAL_MODELS=false
RUN pip install -r /app/p5-deployment/requirements.txt \
    && if [ "$INSTALL_LOCAL_MODELS" = "true" ]; then pip install -r /app/p5-deployment/requirements-local-models.txt; fi \
    && useradd --create-home appuser \
    && mkdir -p /app/p5-deployment/data \
    && chown appuser:appuser /app/p5-deployment/data

COPY --chown=appuser:appuser p5-deployment/app.py /app/p5-deployment/
COPY --chown=appuser:appuser p5-deployment/chat /app/p5-deployment/chat
COPY --chown=appuser:appuser p5-deployment/integrations /app/p5-deployment/integrations
COPY --chown=appuser:appuser p5-deployment/storage /app/p5-deployment/storage
COPY --chown=appuser:appuser p5-deployment/ui /app/p5-deployment/ui
COPY --chown=appuser:appuser p4-agent/p4 /app/p4-agent/p4
COPY --chown=appuser:appuser p4-agent/integration/runtime.py /app/p4-agent/integration/runtime.py
COPY --chown=appuser:appuser p4-agent/integration/p2_agents /app/p4-agent/integration/p2_agents
COPY --chown=appuser:appuser p4-agent/p3_retrieval/retrieve.py /app/p4-agent/p3_retrieval/retrieve.py

USER appuser
EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=3)"

CMD ["streamlit", "run", "p5-deployment/app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]
