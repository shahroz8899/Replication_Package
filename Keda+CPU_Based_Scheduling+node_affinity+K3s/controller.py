import os
import time
import asyncio
import logging
from fastapi import FastAPI
from fastapi.responses import Response
from kubernetes import client, config
from prometheus_client import Gauge, generate_latest, CONTENT_TYPE_LATEST

# -----------------------------------------------------------------------------
# Logging setup
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | controller | %(levelname)s | %(message)s",
)
logger = logging.getLogger("controller")

# -----------------------------------------------------------------------------
# Kubernetes configuration
# -----------------------------------------------------------------------------
try:
    config.load_incluster_config()
    logger.info("✅ Loaded in-cluster kubeconfig")
except Exception:
    config.load_kube_config()
    logger.info("✅ Loaded local kubeconfig from ~/.kube/config")

v1 = client.CoreV1Api()

# -----------------------------------------------------------------------------
# FastAPI + Prometheus setup
# -----------------------------------------------------------------------------
app = FastAPI(title="Posture Controller")

AVAILABLE_NODES = Gauge(
    "available_node_count_30s",
    "Number of eligible nodes with posture/eligible=true in the last 30 s",
)

CPU_THRESHOLD = float(os.getenv("CPU_THRESHOLD", "0.70"))

# -----------------------------------------------------------------------------
# Helper: count eligible nodes
# -----------------------------------------------------------------------------
def count_eligible_nodes():
    nodes = v1.list_node().items
    eligible = []
    for node in nodes:
        labels = node.metadata.labels or {}
        if labels.get("posture/eligible", "false").lower() == "true":
            eligible.append(node.metadata.name)
    return len(eligible), eligible

# -----------------------------------------------------------------------------
# Node labeling loop
# -----------------------------------------------------------------------------
async def label_nodes_loop():
    while True:
        try:
            count, eligible = count_eligible_nodes()
            AVAILABLE_NODES.set(count)
            logger.info(
                f"📊 available_node_count_30s={count} eligible={eligible}"
            )
        except Exception as e:
            logger.error(f"label_nodes_loop error: {e}")
        await asyncio.sleep(30)

# -----------------------------------------------------------------------------
# Prometheus metrics endpoint
# -----------------------------------------------------------------------------
@app.get("/metrics")
def metrics():
    data = generate_latest()
    return Response(data, media_type=CONTENT_TYPE_LATEST)

# -----------------------------------------------------------------------------
# Startup
# -----------------------------------------------------------------------------
@app.on_event("startup")
async def on_startup():
    logger.info("🌿 Launching node-labeler & metrics loop ...")
    asyncio.create_task(label_nodes_loop())
    logger.info("✅ controller: label_nodes_loop started successfully")

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    logger.info("🚀 Starting Posture Controller with /metrics on port 8080 …")
    uvicorn.run(app, host="0.0.0.0", port=8080)
