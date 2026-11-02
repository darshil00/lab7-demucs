#!/usr/bin/env python3

import os
import io
import json
import time
import tempfile
import subprocess
import sys
from pathlib import Path

import redis
import requests
from minio import Minio

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

MINIO_HOST = os.getenv("MINIO_HOST", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "rootuser")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "rootpass123")

QUEUE_BUCKET = "queue"
OUTPUT_BUCKET = "output"
WORK_QUEUE = "toWorker"

TRACKS = ["bass", "drums", "vocals", "other"]

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True,
    socket_connect_timeout=10,
    socket_timeout=None,
    health_check_interval=30
)

minio_client = Minio(
    MINIO_HOST,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)


def log(message):
    print(f"[WORKER] {message}", flush=True)

    try:
        redis_client.lpush("logging", f"[WORKER] {message}")
    except Exception:
        pass


def process_job(job):
    songhash = job["hash"]
    model = job.get("model", "htdemucs")

    if not isinstance(songhash, str) or len(songhash) != 64 or any(
        c not in "0123456789abcdef" for c in songhash
    ):
        raise ValueError("Invalid song hash")

    if model != "htdemucs":
        raise ValueError("Unsupported model")

    log(f"Processing song: {songhash}")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        input_file = temp_path / f"{songhash}.mp3"
        output_dir = temp_path / "output"

        minio_client.fget_object(
            QUEUE_BUCKET,
            f"{songhash}.mp3",
            str(input_file)
        )

        log("Downloaded MP3 from MinIO")

        command = [
            sys.executable,
            "-m",
            "demucs.separate",
            "--device",
            "cpu",
            "-n",
            model,
            "--mp3",
            "--out",
            str(output_dir),
            str(input_file)
        ]

        log("Starting Demucs separation")

        subprocess.run(command, check=True)

        tracks_dir = output_dir / model / songhash

        for track in TRACKS:
            track_file = tracks_dir / f"{track}.mp3"

            if not track_file.is_file():
                raise FileNotFoundError(
                    f"Missing separated track: {track_file}"
                )

            object_name = f"{songhash}-{track}.mp3"

            minio_client.fput_object(
                OUTPUT_BUCKET,
                object_name,
                str(track_file),
                content_type="audio/mpeg"
            )

            log(f"Uploaded {object_name}")

    callback = job.get("callback")

    if isinstance(callback, dict) and callback.get("url"):
        try:
            requests.post(
                callback["url"],
                json=callback.get("data", {}),
                timeout=5
            )
            log("Callback request sent")
        except requests.RequestException as exc:
            log(f"Callback failed (non-fatal): {exc}")

    log(f"Completed song: {songhash}")


def main():
    log("Worker started and waiting for jobs")

    while True:
        try:
            result = redis_client.blpop(WORK_QUEUE, timeout=5)

            if result is None:
                continue

            _, raw_job = result
            job = json.loads(raw_job)

            process_job(job)

        except KeyboardInterrupt:
            log("Worker stopped")
            break

        except Exception as exc:
            log(f"Job processing error: {exc}")
            time.sleep(2)


if __name__ == "__main__":
    main()
