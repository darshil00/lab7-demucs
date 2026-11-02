#!/usr/bin/env python3

import os
import io
import json
import base64
import hashlib

from flask import Flask, request, jsonify, send_file
from redis import Redis
from minio import Minio
from minio.error import S3Error

app = Flask(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
MINIO_HOST = os.getenv("MINIO_HOST", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "rootuser")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "rootpass123")

QUEUE_BUCKET = "queue"
OUTPUT_BUCKET = "output"
WORK_QUEUE = "toWorker"

redis_client = Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True
)

minio_client = Minio(
    MINIO_HOST,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)


@app.route("/", methods=["GET"])
def home():
    return "<h1>Music Separation Server</h1><p>Use a valid endpoint</p>"


@app.route("/apiv1/separate", methods=["POST"])
def separate():

    data = request.get_json(silent=True)

    if not isinstance(data, dict) or "mp3" not in data:
        return jsonify({"error": "Missing mp3 data"}), 400

    try:
        mp3_bytes = base64.b64decode(data["mp3"], validate=True)

        if not mp3_bytes:
            return jsonify({"error": "Empty MP3"}), 400

        songhash = hashlib.sha256(mp3_bytes).hexdigest()

        minio_client.put_object(
            QUEUE_BUCKET,
            songhash + ".mp3",
            io.BytesIO(mp3_bytes),
            length=len(mp3_bytes),
            content_type="audio/mpeg"
        )

        job = {
            "hash": songhash,
            "model": data.get("model", "htdemucs"),
            "callback": data.get("callback")
        }

        redis_client.lpush(WORK_QUEUE, json.dumps(job))

        return jsonify({
            "hash": songhash,
            "reason": "Song enqueued for separation"
        })

    except (ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400

    except Exception as e:
        app.logger.exception("Separation request failed")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/apiv1/queue", methods=["GET"])
@app.route("/apiv1/queue/", methods=["GET"])
def queue():

    jobs = redis_client.lrange(WORK_QUEUE, 0, -1)

    hashes = []

    for job in jobs:
        try:
            hashes.append(json.loads(job)["hash"])
        except (ValueError, KeyError, TypeError):
            hashes.append(job)

    return jsonify({"queue": hashes})


ALLOWED_TRACKS = {"bass.mp3", "vocals.mp3", "drums.mp3", "other.mp3"}


@app.route("/apiv1/track/<songhash>/<track>", methods=["GET"])
def get_track(songhash, track):

    if track not in ALLOWED_TRACKS:
        return jsonify({"error": "Invalid track"}), 400

    if len(songhash) != 64 or any(c not in "0123456789abcdef" for c in songhash):
        return jsonify({"error": "Invalid song hash"}), 400

    object_name = f"{songhash}-{track}"

    try:
        response = minio_client.get_object(OUTPUT_BUCKET, object_name)

        try:
            audio_bytes = response.read()
        finally:
            response.close()
            response.release_conn()

        return send_file(
            io.BytesIO(audio_bytes),
            mimetype="audio/mpeg",
            as_attachment=True,
            download_name=track
        )

    except S3Error as e:
        if e.code in ("NoSuchKey", "NoSuchObject"):
            return jsonify({"error": "Track not found"}), 404
        app.logger.exception("MinIO retrieval failed")
        return jsonify({"error": "Storage error"}), 500


@app.route("/apiv1/remove/<songhash>/<track>", methods=["GET", "DELETE"])
def remove_track(songhash, track):

    if track not in ALLOWED_TRACKS:
        return jsonify({"error": "Invalid track"}), 400

    if len(songhash) != 64 or any(c not in "0123456789abcdef" for c in songhash):
        return jsonify({"error": "Invalid song hash"}), 400

    object_name = f"{songhash}-{track}"

    try:
        minio_client.stat_object(OUTPUT_BUCKET, object_name)
        minio_client.remove_object(OUTPUT_BUCKET, object_name)

        return jsonify({
            "hash": songhash,
            "track": track,
            "reason": "Track removed"
        })

    except S3Error as e:
        if e.code in ("NoSuchKey", "NoSuchObject"):
            return jsonify({"error": "Track not found"}), 404
        app.logger.exception("MinIO removal failed")
        return jsonify({"error": "Storage error"}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
