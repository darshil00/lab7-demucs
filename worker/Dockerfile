FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    demucs \
    numpy \
    redis \
    minio \
    requests

COPY worker-server.py /app/worker-server.py

ENV PYTHONUNBUFFERED=1

CMD ["python", "worker-server.py"]
