# SubFly transcription service — NVIDIA Tesla T4 / CUDA
# Target: Unraid with Nvidia Driver plugin + Docker

FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SUBFLY_HOST=0.0.0.0 \
    SUBFLY_PORT=8765 \
    SUBFLY_MODEL_SIZE=large-v3 \
    SUBFLY_DEVICE=cuda \
    SUBFLY_COMPUTE_TYPE=float16 \
    SUBFLY_LANGUAGE=en \
    SUBFLY_DOWNLOAD_ROOT=/models \
    HF_HOME=/models/hf

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        ffmpeg \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/bin/python

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --upgrade pip \
    && pip3 install -r requirements.txt

COPY app ./app

RUN mkdir -p /models /data

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8765/healthz || exit 1

CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765"]
