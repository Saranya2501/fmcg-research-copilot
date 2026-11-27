FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    RAG_RERANKER_ENABLED=false

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
COPY backend/requirements-local-models.txt /app/backend/requirements-local-models.txt
ARG INSTALL_LOCAL_MODELS=false
RUN pip install -r /app/backend/requirements.txt \
    && if [ "$INSTALL_LOCAL_MODELS" = "true" ]; then pip install -r /app/backend/requirements-local-models.txt; fi \
    && useradd --create-home appuser \
    && mkdir -p /app/backend/data \
    && chown appuser:appuser /app/backend/data

COPY --chown=appuser:appuser backend/app.py /app/backend/
COPY --chown=appuser:appuser backend/chat /app/backend/chat
COPY --chown=appuser:appuser backend/integrations /app/backend/integrations
COPY --chown=appuser:appuser backend/storage /app/backend/storage
COPY --chown=appuser:appuser backend/ui /app/backend/ui
COPY --chown=appuser:appuser retrival/agent /app/retrival/agent
COPY --chown=appuser:appuser retrival/integration/runtime.py /app/retrival/integration/runtime.py
COPY --chown=appuser:appuser retrival/integration/p2_agents /app/retrival/integration/p2_agents
COPY --chown=appuser:appuser retrival/core/retrieve.py /app/retrival/core/retrieve.py

USER appuser
EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=3)"

CMD ["streamlit", "run", "backend/app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]
