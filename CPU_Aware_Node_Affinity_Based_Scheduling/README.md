# CPU‑Aware K3s Scheduler with Node Affinity (Posture Jobs)

> **Goal:** Run 10 independent posture‑analysis **Jobs** (Dockerized Python apps) on a **K3s/Kubernetes** cluster and place their Pods on the **least‑busy nodes** based on **live CPU usage** scraped from **Prometheus** — while respecting **node affinity** via labels.  
> **How it works (high‑level):** a lightweight custom scheduler (`cpu_scheduler.py`) polls Prometheus every few seconds, finds **under‑loaded** nodes (e.g., <90% CPU), and **binds** pending Pods to them. Periodically it **offloads** Pods from overloaded nodes so the Job controller recreates them on less busy nodes.

This document is a **full, start‑to‑finish guide** for non‑experts. It covers cluster setup, Prometheus + Node Exporter, node labels/affinity, building images, creating Jobs, and running the custom scheduler. It uses **placeholders** for any credentials — **do not** paste secrets into files.

---

## Table of Contents

1. [What You’ll Set Up](#what-youll-set-up)
2. [Repository Layout](#repository-layout)
3. [Prerequisites](#prerequisites)
4. [Step 0 — Get the Code](#step-0--get-the-code)
5. [Step 1 — Create (or Use) a K3s/Kubernetes Cluster](#step-1--create-or-use-a-k3skubernetes-cluster)
6. [Step 2 — Install Prometheus + Node Exporter (Helm)](#step-2--install-prometheus--node-exporter-helm)
7. [Step 3 — Verify CPU Metrics and Create a 10s Scrape](#step-3--verify-cpu-metrics-and-create-a-10s-scrape) 
8. [Step 5 — Python Environment](#step-5--python-environment)
9. [Step 6 — Build Images, Apply RBAC/Jobs, Run Scheduler](#step-6--build-images-apply-rbacjobs-run-scheduler)
10. [Step 7 — Observe Scheduling and Outputs](#step-7--observe-scheduling-and-outputs)
11. [Configuration Notes](#configuration-notes)
12. [Troubleshooting](#troubleshooting)


---

## What You’ll Set Up

- **K3s/Kubernetes** cluster with several worker nodes (e.g., `agx-desktop`, `orin-desktop`, `nano1-desktop`, `nano2-desktop`, `orin1-desktop`, `orin2-desktop`).
- **Prometheus** scraping each node via **Node Exporter** (CPU scraped every **10s**).
- **Jobs**: `posture-pi1`, `posture-pi1-1`, …, `posture-pi1-9` (1 Pod each).
- **Custom scheduler**: `cpu_scheduler.py` (uses `schedulerName: cpu-scheduler`) binds **Pending** Pods and periodically **offloads** from overloaded nodes (≥90%).

> The project includes a helper `build.py` that can build multi‑arch images, push to a registry, apply RBAC, create the Jobs, and start the scheduler with one command.

---

## Repository Layout

```
CPU_Aware_Node_Affinity_Based_Scheduling/
├── build.py                        # One-shot build/deploy/run helper
├── cpu_scheduler.py                # Custom CPU-aware binder/offloader (Binding API)
├── cpu_metrics.py                  # Prometheus query & node mapping helpers
├── posture-jobs.yaml               # 10 Jobs (1 Pod each) with schedulerName: cpu-scheduler
├── cpu-scheduler-rbac.yaml         # ServiceAccount + ClusterRole(+Binding) for scheduler
├── Dockerfile                      # Dockerfile for posture analyzers
├── requirements.txt                # Python dependencies for apps + scheduler
├── Images_From_Pi1.py              # Analyzer app (also Images_From_Pi1_1.py ... _9.py)
└── docker-compose.yml              # optional local testing (not required on k8s)
```

> The **RaspberryPi_Script/** (at repo root) captures/sends images; projects can consume them.

---

## Prerequisites

- A **K3s** or **Kubernetes** cluster (control plane + worker nodes).
- **kubectl** installed and pointing to the cluster.
- **Helm 3** installed.
- **Docker** with **Buildx** (for multi‑arch builds) on the machine running `build.py`.
- A container registry account (e.g., Docker Hub). Use **placeholders** — no secrets in the repo:
  - `DOCKER_REGISTRY=registry.hub.docker.com`
  - `DOCKER_NAMESPACE=<your-dockerhub-username>`
- Python **3.10+**.

---

## Step 0 — Get the Code

```bash
git clone https://github.com/shahroz8899/Replication_Package.git
cd Replication_Package/CPU_Aware_Node_Affinity_Based_Scheduling
```

---

## Step 1 — Create (or Use) a K3s/Kubernetes Cluster

If you don’t already have one, **either** create a small lab cluster (on Jetsons/PCs/VMs) or reuse a cloud cluster. For K3s on a Linux host (quick start):

```bash
# On the host that will be the server:
curl -sfL https://get.k3s.io | sh -
# On agents, point to the server (set token/server from your environment securely)
curl -sfL https://get.k3s.io | K3S_URL=https://<server-ip>:6443 K3S_TOKEN=<redacted> sh -

# Confirm nodes:
kubectl get nodes -o wide
```

> **Tip:** Make sure every node shows **Ready** and has working DNS/networking before continuing.

---

## Step 2 — Install Prometheus + Node Exporter (Helm)

Easiest path is the **kube‑prometheus‑stack** Helm chart (includes Prometheus Operator, Prometheus, Alertmanager, Grafana, and **Node Exporter DaemonSet**).

```bash
kubectl create namespace monitoring

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Create a minimal values.yaml overriding the scrape interval to 10s:
cat > values.yaml <<'YAML'
prometheus:
  prometheusSpec:
    scrapeInterval: 10s
    evaluationInterval: 10s
YAML

helm install kube-prom-stack prometheus-community/kube-prometheus-stack \
  -n monitoring -f values.yaml
```

> This deploys **node-exporter** to all nodes automatically.   

Once up, check that Pods are **Running**:

```bash
kubectl get pods -n monitoring -o wide
```

---

## Step 3 — Verify CPU Metrics and Create a 10s Scrape

Open the Prometheus UI (port-forward from your workstation):

```bash
kubectl -n monitoring port-forward svc/kube-prom-stack-prometheus 9090:9090
```

In the **Graph** tab, run a CPU utilization expression based on **node_exporter** metrics:

```
100 - (avg by (instance) (irate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)
```

- Values near **0** mean idle; values near **100** mean fully used.
- The scheduler queries Prometheus over HTTP; keep the service reachable from the machine running `cpu_scheduler.py` (port-forward or cluster DNS if running in‑cluster).

> If you prefer a dedicated job with an explicit 10s scrape, you can create a `ServiceMonitor` or `ScrapeConfig` (Prometheus Operator) targeting `node-exporter` with `scrapeInterval: 10s`.

---


## Step 5 — Python Environment

On the **operator** machine that will run `build.py` (and possibly `cpu_scheduler.py`):

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

> This installs both posture app and scheduler dependencies.

---

## Step 6 — Build Images, Apply RBAC/Jobs, Run Scheduler

Set **safe environment variables** (no secrets checked into git). Example for Docker Hub:

```bash
export DOCKER_NAMESPACE=<your-dockerhub-username>
export IMAGE_TAG=latest
```

Now run the all‑in‑one helper:

```bash
python3 build.py
```

What `build.py` typically does:

- Builds and **pushes** 10 images (multi‑arch with Buildx) for the analyzer apps.
- Applies **RBAC** (`cpu-scheduler-rbac.yaml`) so the scheduler can read Pods/nodes and create **Binding** objects.
- Applies **Jobs** (`posture-jobs.yaml`) which specify `schedulerName: cpu-scheduler`.
- Starts the **custom scheduler**: `python3 cpu_scheduler.py` (can also be run in‑cluster as a Deployment if desired).

> If you prefer manual control, you can split the steps: `kubectl apply -f cpu-scheduler-rbac.yaml`, `kubectl apply -f posture-jobs.yaml`, then run the scheduler separately.

---

## Step 7 — Observe Scheduling and Outputs

Watch Pods being scheduled and started:

```bash
kubectl get pods -l app=posture -o wide -w
```

- Pending Pods should be **bound** to the **least busy** nodes.
- Every ~30s, if a node is ≥90% CPU, the scheduler may **delete** a Pod there; the Job controller will recreate it, and the scheduler will bind it to a less loaded node.

When a Pod completes, it writes a **CSV** result on the node where it ran (exact path is defined in the app). Collect or ship these as needed.

---

## Configuration Notes

- **Thresholds:** Edit the CPU threshold (e.g., 90%) and polling intervals (e.g., 10s/30s) in `cpu_scheduler.py` / `cpu_metrics.py` if needed.
- **Prometheus URL:** The scheduler needs a Prometheus HTTP endpoint. If running outside the cluster, use `kubectl port-forward` (Step 3) or expose Prometheus via a LoadBalancer/Ingress.
- **Node Mapping:** `cpu_metrics.py` associates Prometheus `instance` values to Kubernetes node names. Confirm your mapping aligns (e.g., by hostname or IP).
- **Node Affinity:** Ensure `posture-jobs.yaml` `affinity.nodeAffinity` matches your node labels (Step 4).

---

## Troubleshooting

**Prometheus / metrics**  
- `kubectl -n monitoring get pods` shows all **Running**.  
- Port‑forward Prometheus and run the CPU query. If no data, check that the **node‑exporter** DaemonSet is present and **Targets** are **UP** in Prometheus.  
- If CPU values look wrong, try a window like `[2m]` or `[5m]` in the `irate()` to smooth spiky nodes.

**Scheduler permissions**  
- If the scheduler can’t bind, check RBAC: `kubectl auth can-i create binding --as=system:serviceaccount:<ns>:<sa>`.  
- Ensure the ServiceAccount/ClusterRole/Binding names in `cpu-scheduler-rbac.yaml` match what the scheduler code expects.

**Node affinity / labels**  
- If Pods remain Pending with messages about **node affinity**, re‑check labels:  
  `kubectl get nodes --show-labels | grep device=`  
- Update `posture-jobs.yaml` accordingly, then `kubectl apply -f posture-jobs.yaml`.

**Images / registry**  
- Authenticate to your registry **outside** the repo (no secrets committed):  
  `docker login`  
- If multi‑arch fails, ensure Buildx is set up:  
  `docker buildx create --use`

**Kubeconfig / context**  
- Confirm `kubectl` points to the right cluster: `kubectl config current-context` and `kubectl get nodes`.

**Outputs (CSV)**  
- If CSVs don’t appear, check Pod logs: `kubectl logs <pod>`. Verify mount paths/permissions if writing to hostPaths/PVCs.




---

