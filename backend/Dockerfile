FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models/huggingface \
    FASTEMBED_CACHE_PATH=/models/fastembed

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl libgomp1 && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.8.0 && \
    pip install -r /tmp/requirements.txt
COPY backend/app /app/app
COPY prompts /app/prompts

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

