from pydantic import BaseModel, Field, validator
from typing import Dict
from enum import Enum
import subprocess
import json

class DeploymentTier(str, Enum):
    PRODUCTION = "prod"
    DEVELOPMENT = "dev"

class AppLanguage(str, Enum):
    JAVA = "java"
    GO = "go"
    PYTHON = "python"
    DOTNET = "dotnet"

class HighThroughputAPI(BaseModel):
    app_namespace: str = "perf-test"
    app_name: str
    image_repo: str = "my-docker-reg/app"
    peak_rps: int = Field(..., gt=0, description="Expected peak Requests Per Second")
    latency_sla_ms: int = Field(default=200, description="Target P99 latency")
    tier: DeploymentTier = DeploymentTier.PRODUCTION  # Default to safe prod settings
    monitoring_enabled: bool = True
    metrics_path: str = "/metrics"
    metrics_port: int = 9898
    service_port: int = 80
    container_port: int = 9898
    ingress_host: str = "api.example.com"
    cpu_percent: float = 0.10  # Use 10% of node CPU per pod
    mem_percent: float = 0.15  # Use 15% of node RAM per pod
    language: AppLanguage = AppLanguage.JAVA  # Default can be changed per app

    def _parse_memory_to_mib(self, mem_str: str) -> int:
        """Safe conversion of K8s memory strings (Ki, Mi, Gi) to MiB."""
        # Remove any quotes and whitespace
        mem_str = mem_str.strip().strip('"').strip("'")

        if mem_str.endswith('Ki'):
            return int(mem_str.replace('Ki', '')) // 1024
        if mem_str.endswith('Mi'):
            return int(mem_str.replace('Mi', ''))
        if mem_str.endswith('Gi'):
            return int(mem_str.replace('Gi', '')) * 1024
        # Fallback for plain byte strings
        return int(mem_str) // (1024 * 1024)

    def _get_cluster_capacity(self) -> Dict[str, int]:
        """Fetch total allocatable resources across all nodes."""
        try:
            # Get all nodes' allocatable resources
            cmd = "kubectl get nodes -o json"
            result = subprocess.check_output(cmd, shell=True).decode('utf-8')
            nodes = json.loads(result)['items']

            total_cpu = 0
            total_mem = 0

            for node in nodes:
                alloc = node['status']['allocatable']
                # Standardize units to milliCPU and MiB
                cpu_m = int(alloc['cpu'].replace('m', '')) if 'm' in alloc['cpu'] else int(alloc['cpu']) * 1000
                mem_mib = self._parse_memory_to_mib(alloc['memory'])
                total_cpu += cpu_m
                total_mem += mem_mib

            return {
                "avg_cpu": total_cpu // len(nodes),
                "avg_mem": total_mem // len(nodes),
                "node_count": len(nodes)
            }
        except:
            return {"avg_cpu": 8000, "avg_mem": 16000, "node_count": 1}

    def get_resources(self) -> Dict[str, str]:
        cap = self._get_cluster_capacity()
        # Scale requests based on node average to ensure scheduling fits anywhere
        req_cpu = int(cap['avg_cpu'] * self.cpu_percent)
        req_mem = int(cap['avg_mem'] * self.mem_percent)

        if self.tier == DeploymentTier.PRODUCTION:
            return {
                "cpu_request": f"{req_cpu}m",
                "cpu_limit": f"{req_cpu * 2}m",
                "memory_request": f"{req_mem}Mi",
                "memory_limit": f"{req_mem}Mi",
            }
        else:
            return {
                "cpu_request": f"{req_cpu // 2}m",
                "cpu_limit": f"{req_cpu}m",
                "memory_request": f"{req_mem // 2}Mi",
                "memory_limit": f"{req_mem}Mi"
            }

    def validate_deployment(self):
        """Perform a cluster-wide safety check before generation."""
        cap = self._get_cluster_capacity()
        hpa_manifest = self.get_hpa_config()
        max_pods = hpa_manifest["spec"]["maxReplicas"]

        # Calculate the total CPU footprint of this specific app
        # (Average CPU per pod * Number of replicas)
        total_req_cpu = (cap['avg_cpu'] * self.cpu_percent) * max_pods

        # Define the 'Danger Zone' (80% of total cluster capacity)
        safety_threshold = (cap['avg_cpu'] * cap['node_count'] * 0.8)

        if total_req_cpu > safety_threshold:
            print(f"⚠️  WARNING: Deployment '{self.app_name}' is too large!")
            print(f"At max scale ({max_pods} pods), it needs {total_req_cpu}m.")
            print(f"Cluster Safety Limit is only {safety_threshold}m.")

    def get_hpa_config(self) -> Dict[str, int]:
        # Logic: We assume one pod handles ~200 RPS safely.
        # Min replicas is 3 for High Availability.
        min_pods = max(3, self.peak_rps // 200)
        # Max replicas allows for 2x growth over the peak.
        max_pods = min_pods * 2

        # Target RPS: 1000 requests per second per pod as a scaling threshold
        target_rps = 1000

        return {
            "apiVersion": "autoscaling/v2",
            "kind": "HorizontalPodAutoscaler",
            "metadata": {
                "name": self.app_name,
                "namespace": self.app_namespace,
                "labels": self.get_labels()
            },
            "spec": {
                "scaleTargetRef": {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "name": self.app_name
                },
                "minReplicas": min_pods,
                "maxReplicas": max_pods,
                "metrics": [
                    # Metric 1: CPU Utilization (The 70% 'Golden Ratio' safety net)
                    {
                        "type": "Resource",
                        "resource": {
                            "name": "cpu",
                            "target": {"type": "Utilization", "averageUtilization": 70}
                        }
                    },
                    # Metric 2: Custom RPS Metric (Proactive scaling for high-throughput)
                    {
                        "type": "Pods",
                        "pods": {
                            "metric": {"name": "http_requests_per_second"},
                            "target": {"type": "AverageValue", "averageValue": str(target_rps)}
                        }
                    }
                ]
            }
        }

    def get_monitoring_annotations(self) -> Dict[str, str]:
        if not self.monitoring_enabled:
            return {}
        return {
            "prometheus.io/scrape": "true",
            "prometheus.io/path": self.metrics_path,
            "prometheus.io/port": str(self.metrics_port),
            "performance-tier": "high-throughput"  # Custom label for Grafana filtering
        }

    def get_labels(self) -> Dict[str, str]:
        return {
            "app": self.app_name,
            "tier": "high-throughput",
            "managed-by": "performance-portal"
        }

    def get_probe_config(self) -> Dict[str, int]:
        """Performance-tuned health check parameters."""
        return {
            "initial_delay": 30,  # Give J2EE/monoliths time to warm up
            "period": 10,
            "success_threshold": 1,
            "failure_threshold": 3
        }

    def get_deployment_config(self) -> Dict[str, int]:
        """Calculates initial deployment settings."""
        # Match the HPA min_replicas to avoid scaling "flapping" on deploy
        terminationGracePeriodSeconds = 0
        if self.tier == DeploymentTier.PRODUCTION:
            terminationGracePeriodSeconds = 60
        else:
            terminationGracePeriodSeconds = 30
        hpa_manifest = self.get_hpa_config()
        return {
            "replicas": hpa_manifest["spec"]["minReplicas"]
        }

    def get_networking_config(self) -> Dict[str, Any]:
        return {
            "metrics_path": self.metrics_path,
            "service_port": self.service_port,
            "container_port": self.container_port,
            "ingress_host": self.ingress_host,
            "timeout_seconds": 60 if self.tier == DeploymentTier.PRODUCTION else 30,
            # Production uses 'Local' to reduce hops and preserve Source IP
            "external_policy": "Local" if self.tier == DeploymentTier.PRODUCTION else "Cluster"
        }

    def get_java_opts(self) -> str:
        res = self.get_resources()

        # Extract integers from both strings
        request_mib = int(res["memory_request"].replace("Mi", ""))
        limit_mib = int(res["memory_limit"].replace("Mi", ""))

        # 75% of Request for stability, 75% of Limit for ceiling
        initial_heap = int(request_mib * 0.75)
        max_heap = int(limit_mib * 0.75)

        return (
            f"-Xms{initial_heap}m -Xmx{max_heap}m "
            "-XX:+UseContainerSupport "
            "-XX:MaxRAMPercentage=75.0 "
            "-XshowSettings:vm"  # Shows VM settings (heap, etc.)
        )

    def get_probe_config(self) -> Dict[str, Any]:
        """Language-aware probes to prevent 'Death Spirals' during boot."""
        if self.language == AppLanguage.JAVA:
            return {
                "startup": {"failureThreshold": 30, "periodSeconds": 5}, # 150s window
                "readiness": {"initialDelaySeconds": 0, "periodSeconds": 10},
                "liveness": {"initialDelaySeconds": 0, "periodSeconds": 20}
            }
        # Go/Python/Dotnet defaults
        return {
            "startup": {"failureThreshold": 5, "periodSeconds": 5},
            "readiness": {"initialDelaySeconds": 2, "periodSeconds": 5},
            "liveness": {"initialDelaySeconds": 5, "periodSeconds": 10}
        }

    def get_container_env(self) -> Dict[str, str]:
        """Returns environment variables tailored to the application language."""
        env = {}
        if self.language == AppLanguage.JAVA:
            env["JAVA_OPTS"] = self.get_java_opts()
        elif self.language == AppLanguage.DOTNET:
            env["DOTNET_gcServer"] = "1"  # Optimize for high-throughput server load
        elif self.language == AppLanguage.PYTHON:
            env["PYTHONUNBUFFERED"] = "1"  # Ensure logs are streamed instantly
        return env

    def get_service_monitor(self) -> Dict[str, Any]:
        """Generates a ServiceMonitor for Prometheus scraping."""
        return {
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "ServiceMonitor",
            "metadata": {
                "name": self.app_name,
                "labels": {"release": "prometheus"}  # Matches your Prometheus install
            },
            "spec": {
                "selector": {"matchLabels": {"app": self.app_name}},
                "endpoints": [{
                    "port": "http",
                    "path": "/metrics",
                    "interval": "15s"
                }]
            }
        }

    def get_grafana_dashboard(self) -> Dict[str, Any]:
        """Generates a basic Grafana dashboard JSON for the application."""
        return {
            "dashboard": {
                "title": f"App: {self.app_name} - Performance",
                "panels": [
                    {
                        "title": "Requests Per Second (RPS)",
                        "type": "timeseries",
                        "targets": [{
                            "expr": f'sum(rate(http_requests_total{{namespace="{self.app_namespace}", pod=~"{self.app_name}.*"}}[2m])) by (pod)'
                        }]
                    },
                    {
                        "title": "CPU Utilization",
                        "type": "timeseries",
                        "targets": [{
                            "expr": f'sum(node_namespace_pod_container:container_cpu_usage_seconds_total:sum_irate{{namespace="{self.app_namespace}", pod=~"{self.app_name}.*"}})'
                        }]
                    }
                ]
            }
        }