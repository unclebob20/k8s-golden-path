#!/bin/bash

# Configuration
APP_NAME="performance-test"
NAMESPACE="perf-test"
DURATION="300s"
CONCURRENCY="1000"
# Target URL
URL="http://${APP_NAME}.${NAMESPACE}.svc.cluster.local/cache/set?size=1024"

echo "🚀 Starting load test against ${APP_NAME}..."
echo "⏱️  Duration: ${DURATION} | 👥 Concurrency: ${CONCURRENCY}"

# We use -i (interactive) but NOT -t (tty) to avoid the "Unable to use TTY" error.
# 2Gi memory limit ensures the 2,000 concurrent workers have enough buffer space.
kubectl run load-test-$(date +%s) \
  --image=williamyeh/hey \
  --restart=Never \
  --namespace=default \
  -i --attach=true --rm \
  --overrides='{
    "spec": {
      "containers": [{
        "name": "load-test",
        "image": "williamyeh/hey",
        "args": ["-z", "'"${DURATION}"'", "-c", "'"${CONCURRENCY}"'", "'"${URL}"'"],
        "resources": {
          "requests": {"cpu": "1000m", "memory": "1Gi"},
          "limits": {"cpu": "2000m", "memory": "2Gi"}
        }
      }]
    }
  }'