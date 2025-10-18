# KEDA + CPU‑Based Scheduling + Node Affinity on K3s (ScaledJobs)

This project runs **10 posture‑analysis jobs** on a **K3s/Kubernetes** cluster using **KEDA ScaledJob**. 
Pods are **queued and released** based on available capacity and scheduled to nodes via **node affinity**. 
It reuses analyzer scripts (`Images_From_Pi1.py` … `_9.py`) and avoids secrets by design.

> **What’s special here**
> - Uses **KEDA ScaledJob** (10 jobs) — one queued “work item” per analyzer image.
> - Requires node labels: **`posture/eligible=true`** to permit scheduling and a **`posture/slot=slot-N`** preference for spreading/ordering.
> - Deploys an **external scaler** service (`posture-external-scaler`) via `build.py` and a small **FastAPI controller** (`controller.py`) exporting `/metrics`.
> - Analyzer images are built per script and pushed as `#####/posture-analyzer-pi1-{0..9}:latest` by default (configurable).

---

## Table of Contents

1. [Folder Layout](#folder-layout)  
2. [Prerequisites](#prerequisites)  
3. [Quick Start](#quick-start)  
4. [Node Labels (Affinity Rules)](#node-labels-affinity-rules)  
5. [How Scaling Works](#how-scaling-works)  
6. [Analyzer Configuration (MQTT, Output, DB)](#analyzer-configuration-mqtt-output-db)  
7. [Verification](#verification)  
8. [Troubleshooting](#troubleshooting)  
9. [Safety & Privacy](#safety--privacy)

---

## Folder Layout

```
Keda+CPU_Based_Scheduling+node_affinity+K3s/
├── Dockerfile                    # builds analyzer image; selects script via ARG APP
├── Images_From_Pi1.py            # analyzer script (also ..._1.py ... _9.py)
├── build.py                      # builds images, deploys external scaler & ScaledJobs
├── controller.py                 # FastAPI + Prometheus /metrics exporter
├── requirements.txt              # numpy, opencv, mediapipe, paho-mqtt, psutil, psycopg2-binary
├── scaledjob.yaml                # single ScaledJob template (eligible + slot preference)
├── scaledjobs-all.yaml           # 10 ScaledJobs (posture-analyzer-job-0..9)
├── schedueling-rule.txt          # design/notes for queue/release/scheduling
└── stop.py                       # cleanup helper (delete jobs/pods/scaler)
```

> All KEDA resources deploy to namespace **`posture`** (default).

---

## Prerequisites

- A working **K3s/Kubernetes** cluster with `kubectl` access.
- **Helm 3** (to install KEDA; Prometheus is optional for this project).
- **Docker** with **Buildx** (images are built for `linux/arm64/v8` by default).
- A container registry account (e.g., Docker Hub).

**Install KEDA** (once per cluster):
```bash
helm repo add kedacore https://kedacore.github.io/charts
helm repo update
helm install keda kedacore/keda -n keda --create-namespace
kubectl get pods -n keda
```

---

## Quick Start

Clone and enter the project:
```bash
git clone https://github.com/shahroz8899/Replication_Package.git
cd Replication_Package/Keda+CPU_Based_Scheduling+node_affinity+K3s
```
pip install -r requirements.txt  # includes prometheus_client, fastapi, uvicorn, kubernetes

pip install -r requirements-local.txt

### 1) Label nodes (once)
See [Node Labels](#node-labels-affinity-rules). You **must** set:
- `posture/eligible=true` on nodes allowed to run analyzers.
- `posture/slot=slot-N` (N = 1..10) to set preference order for spreading.

### 2) Build & deploy (one command)
`build.py` builds the external scaler image (or reuses the default), builds **10 analyzer images**, creates the namespace and a ConfigMap, deploys the **external scaler** (Deployment + Service) and applies all **10 ScaledJobs**.

```bash
# (Optional) Customize defaults via env vars
export NAMESPACE=posture
export ANALYZER_REPO_BASE="<your-docker-namespace>/posture-analyzer-pi1"
export SCALER_IMAGE_REPO="<your-docker-namespace>/posture-external-scaler"
export CPU_THRESHOLD="0.70"          # used by the scaler
export METRIC_NAME="available_node_count_30s"
export PROM_URL="http://<prometheus-svc>:9090"  # if you use Prometheus in the scaler

# Build & deploy everything:
python3 build.py
```

What this does (from `build.py`):
- Ensures namespace **`posture`** and creates a `prometheus-config` **ConfigMap** with `PROM_URL`.
- Deploys the external scaler as a **Deployment** `posture-external-scaler` + **Service** on port **8080**.  
  Env given to the scaler: `PROM_URL`, `CPU_THRESHOLD`, `METRIC_NAME`, `CONTROLLER_URL` (defaults inside `build.py`).
- Builds and **pushes** 10 analyzer images from **one Dockerfile** by swapping `APP` build‑arg:
  `ANALYZER_REPO_BASE` → `ANALYZER_REPO_BASE-{i}:latest` for i = 0..9.
- Applies **10 KEDA ScaledJobs** from `scaledjobs-all.yaml` in namespace **posture**.

To **stop/cleanup** later:
```bash
python3 stop.py
# or manually:
kubectl -n posture delete scaledjob --all
kubectl -n posture delete job --all
kubectl -n posture delete deploy posture-external-scaler
kubectl -n posture delete svc posture-external-scaler
```

---

## Node Labels (Affinity Rules)

The ScaledJobs use **node affinity** that **requires** `posture/eligible=true` and **prefers** a slot order via `posture/slot=slot-N` (higher weight for lower slots). Example from `scaledjobs-all.yaml`:

```yaml
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
        - matchExpressions:
            - key: posture/eligible
              operator: In
              values: ["true"]
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        preference:
          matchExpressions:
            - key: posture/slot
              operator: In
              values: ["slot-1"]
      - weight: 90
        preference:
          matchExpressions:
            - key: posture/slot
              operator: In
              values: ["slot-2"]
      - weight: 80
        preference:
          matchExpressions:
            - key: posture/slot
              operator: In
              values: ["slot-3"]
      # ... continues down to slot-10 with decreasing weight
```

**Label nodes** (once), mapping each node to exactly one slot:
```bash
# Mark nodes eligible:
kubectl label nodes <nrk nodes eliode-a> posture/eligible=true
kubectl label nodes <node-b> posture/eligible=true
# ...repeat for all nodes allowed to run jobs

# Assign unique slots (1..10) to influence preference order:
kubectl label nodes <node-a> posture/slot=slot-1 --overwrite
kubectl label nodes <node-b> posture/slot=slot-2 --overwrite
# ... up to slot-10 (adjust count to your cluster size)

# Inspect:
kubectl get nodes --show-labels | grep posture/
```

---

## How Scaling Works

**KEDA ScaledJob** (see `scaledjobs-all.yaml`):
- **pollingInterval:** `10s`
- **maxReplicaCount:** `1` per ScaledJob (so at most 10 Pods total when all nodes are available)
- **triggers:** `type: external` with
  - `scalerAddress: posture-external-scaler.posture.svc.cluster.local:8080`
  - `metricName: available_node_count_30s`

**External Scaler**
- Deployed by `build.py` as **Deployment** + **Service** (`posture-external-scaler:8080`).
- It evaluates availability (CPU threshold, etc.) and exposes the value to KEDA via the external scaler interface.
- `build.py` passes environment variables: `PROM_URL`, `CPU_THRESHOLD`, `METRIC_NAME`, `CONTROLLER_URL`.

**Controller (`controller.py`)**
- Runs a **FastAPI** app that exports **Prometheus metrics** at `GET /metrics`.
- Every **30s**, it counts nodes with `posture/eligible=true` and updates the gauge **`available_node_count_30s`**.


---

## Analyzer Configuration (MQTT, Output, DB)

All analyzer containers are built from a **single `Dockerfile`**; the specific script is selected by build arg `APP` (e.g., `Images_From_Pi1_3.py`). Key environment variables in `Images_From_Pi1.py` (and siblings):

- **MQTT input**  
  `MQTT_BROKER` (default e.g., `192.168.x.x`), `MQTT_PORT` (default `1883`), `MQTT_TOPIC` (default `images/#`).

- **Output paths**  
  `OUTPUT_DIR` (default `./analyzed_images`) for per‑node outputs;  
  `CSV_PATH` (default e.g., `pi1_results.csv`) for results.

- **Parallelism**  
  `NUM_WORKERS` (defaults to CPU count).

- **(Optional) Database**  
  The scripts include DB parameters (`DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_PORT`, `DB_SSLMODE`) and a flag **`DB_ENABLED`**.  
  **By default set `DB_ENABLED=false`** so **no DB writes occur**.  
  If you need DB logging, **override via env vars at runtime** — **do not** commit any credentials.

> You can inject env vars into the Pod templates in `scaledjobs-all.yaml` under `spec.jobTargetRef.template.spec.containers[0].env`.

---

## Verification

Check KEDA and the ScaledJobs:
```bash
kubectl get pods -n posture -o wide
kubectl get scaledjobs.keda.sh -n posture
kubectl describe scaledjob posture-analyzer-job-0 -n posture
```

Check the scaler & metric endpoint:
```bash
kubectl get deploy,svc -n posture | grep posture-external-scaler
kubectl -n posture port-forward svc/posture-external-scaler 8080:8080
# (In another shell) curl http://localhost:8080/  # external scaler gRPC/health (impl-dependent)

# Controller metrics (if running):
curl http://<controller-host>:8080/metrics | grep available_node_count_30s
```

Observe that at most **one job per eligible node** is released at a time (subject to your CPU threshold and slot preferences).

---

## Troubleshooting

- **Pods pending / not scheduled**  
  Ensure nodes are labeled: `posture/eligible=true`. Check affinity events with:  
  `kubectl describe pod <name> -n posture`

- **Jobs not scaling up**  
  `kubectl get pods -n keda` → KEDA operator must be Running.  
  Verify external scaler **Service** is reachable: `posture-external-scaler.posture.svc:8080`.  
  Confirm controller/scaler metric **`available_node_count_30s`** increases when you label more nodes.

- **Analyzer images**  
  Make sure you’re logged into your registry. If you change `ANALYZER_REPO_BASE`, rebuild: `python3 build.py`.

- **DB writes**  
  Keep `DB_ENABLED=false` unless you’ve intentionally provided secure DB settings via env vars. Never commit credentials.

- **Cleanup**  
  `python3 stop.py` (or the manual delete commands noted above).

---

