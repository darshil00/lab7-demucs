# Lab 7 — Music Separation Using Kubernetes

## Objective

Build a Kubernetes-based REST service that separates MP3 songs into four tracks using Demucs.

## Architecture

Client → REST API → Redis Queue → Demucs Worker → MinIO Output

- REST: Accepts MP3 files, generates SHA-256 hashes, and queues jobs.
- Redis: Passes processing requests to the worker.
- MinIO: Stores original MP3 files and separated tracks.
- Worker: Uses Demucs (`htdemucs`) to separate audio.
- Kubernetes: Deploys and manages the services.

## Deployment

### Local
- Windows + WSL Ubuntu
- Docker Desktop Kubernetes
- REST, Worker, Redis, MinIO and NGINX ingress tested successfully.

### Google Cloud
- Project: `alien-gantry-506723-p1`
- Cluster: `lab7-demucs-cluster`
- Zone: `us-central1-c`
- Machine: `n2-standard-4`
- Nodes: 1
- CPU: 4 vCPUs
- RAM: 16 GiB
- Node disk: 100 GB
- MinIO persistent storage: 20 GiB

Docker images stored in Artifact Registry:
- `demucs-rest:v1`
- `demucs-worker:v2`

## GKE Deployment Results

All four deployments successfully running:

| Deployment | Ready | Status |
|---|---|---|
| demucs-worker | 1/1 | Running |
| minio | 1/1 | Running |
| redis | 1/1 | Running |
| rest-server | 1/1 | Running |

All four pods reported zero restarts.

## Music Separation Test

Input: `data/short-hop.mp3`

SHA-256:

`9627ed8f6b9ddd5b86fa495161a6de2ab371e2ed8e052d659a88c51272b4fc28`

Worker successfully:
1. Received the Redis job.
2. Downloaded the MP3 from MinIO.
3. Executed Demucs separation.
4. Uploaded all four tracks.
5. Completed processing.

### Output Files

| Track | Size | HTTP Status | MP3 Header |
|---|---|---|---|
| bass.mp3 | 415869 bytes | 200 | PASS |
| drums.mp3 | 415869 bytes | 200 | PASS |
| vocals.mp3 | 415869 bytes | 200 | PASS |
| other.mp3 | 415869 bytes | 200 | PASS |

Total downloaded output: approximately 1.6 MiB.

## Redis and MinIO Verification

- Redis queue length after processing: `0`
- MinIO buckets: `queue`, `output`
- MinIO PVC: `minio-data`
- PVC status: `Bound`
- Storage capacity: `20Gi`
- Storage class: `standard-rwo`

## Issues Resolved

| Issue | Solution |
|---|---|
| GKE stockout in us-central1-a/b | Used n2-standard-4 in us-central1-c |
| MinIO persistent disk permission denied | Configured fsGroup 65532 |
| Worker Python executable not found | Used sys.executable |
| Redis socket timeout | Updated worker Redis connection handling |

## Verification Commands

```bash
kubectl get deployments
kubectl get pods
kubectl logs deployment/demucs-worker --tail=20
kubectl exec deployment/redis -- redis-cli LLEN toWorker
kubectl get pvc
kubectl port-forward service/rest-service 5000:5000
curl http://localhost:5000/apiv1/queue
```

## Result

Successfully deployed and tested the music separation service locally and on Google Kubernetes Engine.

All four separated MP3 tracks were generated, stored in MinIO, and downloaded successfully.

## Repository

https://github.com/darshil00/lab7-demucs
