FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY p5-deployment/requirements.txt /app/p5-deployment/requirements.txt
RUN pip install -r /app/p5-deployment/requirements.txt \
    && useradd --create-home appuser \
    && mkdir -p /app/p5-deployment/data \
    && chown appuser:appuser /app/p5-deployment/data

COPY --chown=appuser:appuser p5-deployment/app.py /app/p5-deployment/app.py
COPY --chown=appuser:appuser p5-deployment/tracing.py /app/p5-deployment/tracing.py

USER appuser
EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=3)"

CMD ["streamlit", "run", "p5-deployment/app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]
