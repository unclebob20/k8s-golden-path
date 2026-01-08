# Kubernetes Proactive Performance Scaler
This repository contains a Python-based manifest generator that produces "Golden Path" Kubernetes deployments. It creates high-performance applications with **Proactive Scaling** based on both CPU and Requests Per Second (RPS) using Prometheus metrics.

## 🚀 Quick Start
### 1. Install Python dependencies:
```
pip install jinja2 pyyaml
```
### 2. Generate your manifests:
```
python main.py --name performance-test --namespace perf-test --profile high-throughput
```
### 3. Deploy to Kubernetes:
```
kubectl apply -f output/performance-test-combined.yaml
```
## 🛠 Command Line Arguments
|Argument   |Description                                |Default
|---------  |-----------                                |-------
|`--name`   |The name of the application and Kubernetes resources.|`performance-test`            
|`--lang`|Programming language profile: `java`, `go`, `python`, or `dotnet`.|`java`
|`--rps`|Expected peak Requests Per Second. Used to calculate HPA scaling thresholds.|`100`
|`--image`|The Docker image repository for the deployment.|`my-docker-reg/app|`
|`--tier`|Deployment environment: `prod` (Safe settings) or `dev` (Cost-optimized).|`prod`
|`--latency`|Target P99 latency in milliseconds.|`200`

## 📊 Infrastructure Setup
To use the **ServiceMonitor** and **RPS Scaling** features, your cluster needs the Prometheus Operator.
### 1. Install Prometheus & Grafana
```
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace
```
### 2. Verify Scrape Targets
Once your app is deployed, check if Prometheus is "seeing" your application:
1. Port-forward Prometheus: `kubectl port-forward svc/prometheus-operated -n monitoring 9090O`
2. Open `localhost:9090` -> **Status** -> **Targets.**
3. Look for `serviceMonitor/perf-test/performance-test` entry.

## 📈 Monitoring & Dashboards
The generator automatically creates a Grafana Dashboard JSON in the `output/` directory.
### 1. Get Grafana Password:
```
kubectl get secret -n monitoring prometheus-stack-grafana -o jsonpath="{.data.admin-password}" | base64 --decode ; echo
```
### 2. Access Grafana: 
`kubectl port-forward svc/prometheus-stack-grafana -n monitoring 3000:80`
### 3.Import Dashboard: 
Copy the content of performance-test-dashboard.json and paste it into Grafana's Import section.

## 🧪 Load Testing
A helper script is provided to simulate high traffic and trigger the autoscaler.
Note: Ensure you have at least 2Gi of memory available for the load-test pod to prevent OOMKilled errors when running with high concurrency.Bash# Make the script executable
```
chmod +x run-load-test.sh

# Run the test (300 seconds, 2000 concurrent workers)
./run-load-test.sh
```
### 🏗 Project Structure
- `main.py`: CLI entry point that handles arguments and file generation.
- `profiles.py`: Contains the logic for different scaling profiles (HPA v2 and ServiceMonitor definitions).
- `templates/`: Jinja2 templates for Deployment and Service
- `output/`: Generated YAML and JSON files ready for kubectl apply.
