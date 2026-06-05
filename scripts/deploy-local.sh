#!/usr/bin/env bash
# =============================================================================
# deploy-local.sh — Full local k3s deployment for Sketch to Story
#
# Usage:
#   ./scripts/deploy-local.sh           # create cluster + deploy
#   ./scripts/deploy-local.sh teardown  # delete cluster
#
# Prerequisites:
#   brew install k3d helm kubectl
# =============================================================================

set -euo pipefail

CLUSTER_NAME="daphne-local"
KEDA_VERSION="2.14.0"
CHART_DIR="$(cd "$(dirname "$0")/../helm/comic-platform" && pwd)"
NAMESPACES_FILE="$(cd "$(dirname "$0")/.." && pwd)/namespaces.yaml"
KEDA_MANIFEST="$(cd "$(dirname "$0")/../keda" && pwd)/scaled-object.yaml"

# -----------------------------------------------------------------------
# Teardown
# -----------------------------------------------------------------------
if [[ "${1:-}" == "teardown" ]]; then
  echo "--- Deleting k3d cluster: ${CLUSTER_NAME}"
  k3d cluster delete "${CLUSTER_NAME}" || true
  echo "--- Cluster deleted."
  exit 0
fi

# -----------------------------------------------------------------------
# 1. Create k3d cluster (maps host port 8080 → k3s ingress 80)
# -----------------------------------------------------------------------
if k3d cluster list | grep -q "${CLUSTER_NAME}"; then
  echo "--- k3d cluster '${CLUSTER_NAME}' already exists, skipping create."
else
  echo "--- Creating k3d cluster: ${CLUSTER_NAME}"
  k3d cluster create "${CLUSTER_NAME}" \
    --port "8080:80@loadbalancer" \
    --agents 2
fi

# Ensure kubeconfig is pointing at our cluster.
k3d kubeconfig merge "${CLUSTER_NAME}" --kubeconfig-switch-context

# -----------------------------------------------------------------------
# 2. Create namespaces
# -----------------------------------------------------------------------
echo "--- Applying namespaces"
kubectl apply -f "${NAMESPACES_FILE}"

# -----------------------------------------------------------------------
# 3. Install KEDA via Helm
# -----------------------------------------------------------------------
if helm status keda -n keda >/dev/null 2>&1; then
  echo "--- KEDA already installed, skipping."
else
  echo "--- Installing KEDA ${KEDA_VERSION}"
  helm repo add kedacore https://kedacore.github.io/charts
  helm repo update
  kubectl create namespace keda --dry-run=client -o yaml | kubectl apply -f -
  helm install keda kedacore/keda \
    --namespace keda \
    --version "${KEDA_VERSION}" \
    --wait
fi

# -----------------------------------------------------------------------
# 4. Deploy the comic-platform Helm chart
# -----------------------------------------------------------------------
echo "--- Deploying comic-platform Helm chart"
helm upgrade --install comic-platform "${CHART_DIR}" \
  --namespace team-comics \
  --create-namespace \
  --set secrets.minioAccessKey="${MINIO_ACCESS_KEY:-minioadmin}" \
  --set secrets.minioSecretKey="${MINIO_SECRET_KEY:-minioadmin}" \
  --wait \
  --timeout 5m

# -----------------------------------------------------------------------
# 5. Apply KEDA ScaledObject
# -----------------------------------------------------------------------
echo "--- Applying KEDA ScaledObject"
kubectl apply -f "${KEDA_MANIFEST}"

# -----------------------------------------------------------------------
# 6. Patch /etc/hosts for comics.local
# -----------------------------------------------------------------------
INGRESS_IP="127.0.0.1"
HOST_ENTRY="${INGRESS_IP} comics.local"

if grep -q "comics.local" /etc/hosts; then
  echo "--- /etc/hosts already has comics.local entry, skipping."
else
  echo "--- Adding '${HOST_ENTRY}' to /etc/hosts (requires sudo)"
  echo "${HOST_ENTRY}" | sudo tee -a /etc/hosts > /dev/null
fi

# -----------------------------------------------------------------------
# Done
# -----------------------------------------------------------------------
echo ""
echo "=== Deployment complete ==="
echo "  API:     http://comics.local:8080"
echo "  Health:  http://comics.local:8080/health"
echo "  Metrics: http://comics.local:8080/metrics"
echo ""
echo "To tear down: ./scripts/deploy-local.sh teardown"
