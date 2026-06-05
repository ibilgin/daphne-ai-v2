Generate a complete Helm chart and k8s manifests for a FastAPI + Celery comic generation service on k3s.

Create:
1. helm/comic-platform/Chart.yaml and values.yaml — configurable: image tags, replica counts, resource limits, Redis URL, MLflow tracking URI, namespace names.

2. helm/comic-platform/templates/:
   - deployment-api.yaml: FastAPI deployment, 2 replicas, readiness probe on /health, liveness on /metrics, resource limits CPU:500m/1, memory:512Mi/1Gi.
   - deployment-worker.yaml: Celery worker deployment, starts at 1 replica (KEDA will scale), resource limits CPU:1/2, memory:1Gi/2Gi.
   - service-api.yaml + ingress.yaml: ClusterIP service, Ingress for comics.local.
   - configmap.yaml: non-secret config (MLflow URI, Ollama endpoint, model aliases).
   - secret.yaml: MinIO credentials (values from Helm --set).
   - rbac.yaml: ServiceAccount, Role (get/list/watch pods and configmaps only), RoleBinding — scoped to team-comics namespace.
   - resourcequota.yaml + limitrange.yaml for team-comics namespace.

3. keda/scaled-object.yaml — ScaledObject for the Celery worker deployment: trigger type redis, listName celery, listLength 5, minReplicaCount 1, maxReplicaCount 6, cooldownPeriod 60.

4. namespaces.yaml — team-comics and team-platform with labels.

5. scripts/deploy-local.sh — creates k3d cluster, installs KEDA via Helm, deploys the chart, patches /etc/hosts for comics.local.