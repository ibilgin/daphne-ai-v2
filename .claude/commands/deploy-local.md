---
description: Full local k3s deployment — creates k3d cluster, installs KEDA, deploys Helm chart, patches /etc/hosts. Usage: /deploy-local or /deploy-local teardown
---

Deploy the Sketch to Story platform to a local k3s cluster.

**Mode**: $ARGUMENTS (empty = deploy, "teardown" = destroy cluster)

---

### TEARDOWN mode (if $ARGUMENTS = "teardown")

```bash
k3d cluster delete comics-lab
# Remove /etc/hosts entry
sudo sed -i '' '/comics.local/d' /etc/hosts
echo "Cluster deleted."
```

---

### DEPLOY mode (default)

**Pre-flight checks**:
```bash
k3d version || { echo "k3d not installed. Run: brew install k3d"; exit 1; }
kubectl version --client || { echo "kubectl not installed. Run: brew install kubectl"; exit 1; }
helm version || { echo "helm not installed. Run: brew install helm"; exit 1; }
ls helm/comic-platform/Chart.yaml || { echo "Phase 2 not implemented. Run /implement-phase 2 first."; exit 1; }
```

**Step 1 — Create k3d cluster**:
```bash
k3d cluster list | grep comics-lab && echo "Cluster already exists — skipping create" || \
k3d cluster create comics-lab \
  --port "8080:80@loadbalancer" \
  --agents 1 \
  --wait
```

**Step 2 — Set kubectl context**:
```bash
kubectl config use-context k3d-comics-lab
kubectl cluster-info
```

**Step 3 — Install KEDA**:
```bash
helm repo add kedacore https://kedacore.github.io/charts --force-update
helm repo update
kubectl get namespace keda 2>/dev/null || \
helm install keda kedacore/keda \
  --namespace keda \
  --create-namespace \
  --wait \
  --timeout 3m
```

**Step 4 — Create namespaces**:
```bash
kubectl apply -f helm/comic-platform/namespaces.yaml 2>/dev/null || \
kubectl create namespace team-comics --dry-run=client -o yaml | kubectl apply -f -
kubectl create namespace team-platform --dry-run=client -o yaml | kubectl apply -f -
```

**Step 5 — Deploy Helm chart**:
```bash
helm upgrade --install comic-platform ./helm/comic-platform \
  --namespace team-comics \
  --set minio.accessKey=minioadmin \
  --set minio.secretKey=minioadmin \
  --set mlflow.trackingUri=http://host.k3d.internal:5001 \
  --set ollama.baseUrl=http://host.k3d.internal:11434 \
  --wait \
  --timeout 5m
```

**Step 6 — Apply KEDA ScaledObject**:
```bash
kubectl apply -f keda/scaled-object.yaml -n team-comics
```

**Step 7 — Patch /etc/hosts**:
```bash
grep -q "comics.local" /etc/hosts || echo "127.0.0.1 comics.local" | sudo tee -a /etc/hosts
```

**Step 8 — Verify deployment**:
```bash
kubectl get pods -n team-comics -w --timeout=120s
kubectl get ingress -n team-comics
kubectl get scaledobject -n team-comics
```

**Report**:
- Pod statuses in team-comics namespace
- Ingress URL: http://comics.local:8080
- KEDA ScaledObject status
- Next step: `curl http://comics.local:8080/health` to verify the API is reachable
