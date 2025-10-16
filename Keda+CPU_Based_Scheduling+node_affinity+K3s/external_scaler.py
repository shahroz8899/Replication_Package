import os
import asyncio
import logging
import grpc
from concurrent import futures
import external_scaler_pb2 as pb2
import external_scaler_pb2_grpc as pb2_grpc
import requests

# -----------------------------------------------------------------------------
# Logging setup
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | scaler | %(levelname)s | %(message)s",
)
logger = logging.getLogger("scaler")

# -----------------------------------------------------------------------------
# Environment
# -----------------------------------------------------------------------------
PROM_URL = os.getenv("PROM_URL", "http://localhost:9090")
METRIC_NAME = os.getenv("METRIC_NAME", "available_node_count_30s")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "8081"))
HOST_IP = "0.0.0.0"

# -----------------------------------------------------------------------------
# gRPC Servicer
# -----------------------------------------------------------------------------
class ExternalScalerServicer(pb2_grpc.ExternalScalerServicer):
    def GetMetricSpec(self, request, context):
        """Describe which metric KEDA should poll"""
        logger.info(f"MetricSpec requested: {METRIC_NAME}")
        spec = pb2.MetricSpec(metric_name=METRIC_NAME, target_size=1)
        return pb2.GetMetricSpecResponse(metric_specs=[spec])

    def IsActive(self, request, context):
        """Whether scaling should be active"""
        try:
            value = self._query_prometheus()
            active = value > 0
            logger.info(f"IsActive check: {METRIC_NAME}={value:.3f} active={active}")
            return pb2.IsActiveResponse(result=active)
        except Exception as e:
            logger.error(f"IsActive error: {e}")
            return pb2.IsActiveResponse(result=False)

    def GetMetrics(self, request, context):
        """Return the metric’s current value"""
        try:
            value = self._query_prometheus()
            value = float(value)
            logger.info(f"GetMetrics -> {METRIC_NAME}: {value:.3f}")
            metric_value = pb2.MetricValue(
                metric_name=METRIC_NAME,
                metric_value=int(value)  # ✅ convert safely to int
            )
            return pb2.GetMetricsResponse(metric_values=[metric_value])
        except Exception as e:
            logger.error(f"GetMetrics error: {e}")
            return pb2.GetMetricsResponse(metric_values=[])

    # -------------------------------------------------------------------------
    def _query_prometheus(self):
        """Query Prometheus for our metric"""
        query_url = f"{PROM_URL}/api/v1/query"
        params = {"query": METRIC_NAME}
        resp = requests.get(query_url, params=params, timeout=5)
        data = resp.json()
        if data.get("status") != "success" or not data["data"]["result"]:
            return 0.0
        return float(data["data"]["result"][0]["value"][1])

# -----------------------------------------------------------------------------
# Server bootstrap
# -----------------------------------------------------------------------------
async def serve():
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    pb2_grpc.add_ExternalScalerServicer_to_server(ExternalScalerServicer(), server)
    server.add_insecure_port(f"{HOST_IP}:{LISTEN_PORT}")
    await server.start()
    logger.info(f"✅ External Scaler running locally at {HOST_IP}:{LISTEN_PORT}")
    await server.wait_for_termination()

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    asyncio.run(serve())
