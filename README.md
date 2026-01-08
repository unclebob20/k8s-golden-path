# Kubernetes Proactive Performance Scaler
This repository contains a Python-based manifest generator that produces "Golden Path" Kubernetes deployments. It creates high-performance applications with **Proactive Scaling** based on both CPU and Requests Per Second (RPS) using Prometheus metrics.

## 🚀 Quick Start
1. Install Python dependencies:
```
pip install jinja2 pyyaml
```
2. Generate your manifests:
```
python main.py --name performance-test --namespace perf-test --profile high-throughput
```
3. Deploy to Kubernetes:
```
kubectl apply -f output/performance-test-combined.yaml
```
## 🛠 Command Line Arguments
|Argument   |Description                                |Default
|---------  |-----------                                |-------
|--name     |The name of the application and Kubernetes resources.|performance-test
             
|--namespaceThe K8s namespace where the app will be deployed.default--profileThe scaling profile to use (high-throughput or standard).high-throughput--outputThe directory where generated files are saved.output/📊 Infrastructure SetupTo use the ServiceMonitor and RPS Scaling features, your cluster needs the Prometheus Operator.1. Install Prometheus & GrafanaUse the official Helm chart to install the full monitoring stack:Bashhelm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace
2. Verify Scrape TargetsOnce your app is deployed, check if Prometheus is "seeing" it:Port-forward Prometheus: kubectl port-forward svc/prometheus-operated -n monitoring 9090Open localhost:9090 -> Status -> Targets.Look for serviceMonitor/perf-test/performance-test.📈 Monitoring & DashboardsThe generator automatically creates a Grafana Dashboard JSON in the output/ directory.Get Grafana Password:Bashkubectl get secret -n monitoring prometheus-stack-grafana -o jsonpath="{.data.admin-password}" | base64 --decode ; echo
Access Grafana: kubectl port-forward svc/prometheus-stack-grafana -n monitoring 3000:80Import Dashboard: Copy the content of performance-test-dashboard.json and paste it into Grafana's Import section.🧪 Load TestingA helper script is provided to simulate high traffic and trigger the autoscaler.Note: Ensure you have at least 2Gi of memory available for the load-test pod to prevent OOMKilled errors when running with high concurrency.Bash# Make the script executable
chmod +x run-load-test.sh

# Run the test (300 seconds, 2000 concurrent workers)
./run-load-test.sh
🏗 Project Structuremain.py: The entry point that handles arguments and file generation.profiles.py: Contains the logic for different scaling profiles (HPA v2 and ServiceMonitor definitions).templates/: Jinja2 templates for Deployment and Service resources.output/: Generated YAML and JSON files ready for kubectl apply.
