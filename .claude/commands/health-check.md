---
description: Check the status of all local services for the Sketch to Story platform — Docker containers, API endpoints, k3s pods, Ollama models. Usage: /health-check
---

Check the health of all Sketch to Story platform services.

Run these checks and report status for each service:

**1. Docker services** (base stack):
```bash
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null
```
Expected: mlflow, minio, postgres, redis all in "running" state.

**2. MLflow API**:
```bash
curl -s --max-time 3 http://localhost:5001/health | python3 -m json.tool 2>/dev/null || echo "UNREACHABLE"
```

**3. MinIO**:
```bash
curl -s --max-time 3 http://localhost:9001/minio/health/live | head -1 || echo "UNREACHABLE"
```

**4. FastAPI**:
```bash
curl -s --max-time 3 http://localhost:8000/health | python3 -m json.tool 2>/dev/null || echo "UNREACHABLE"
curl -s --max-time 3 http://localhost:8000/metrics | head -5 || echo "METRICS UNREACHABLE"
```

**5. Ollama**:
```bash
curl -s --max-time 3 http://localhost:11434/api/tags | python3 -c "import sys,json; d=json.load(sys.stdin); [print(f'  {m[\"name\"]}') for m in d.get('models',[])]" || echo "UNREACHABLE"
```
Expected models loaded: mistral, (optionally llava).

**6. Monitoring stack**:
```bash
docker compose -f monitoring/docker-compose-monitoring.yml ps --format "table {{.Name}}\t{{.Status}}" 2>/dev/null || echo "Not started"
curl -s --max-time 3 http://localhost:3000/api/health | python3 -c "import sys,json; print('Grafana:', json.load(sys.stdin).get('database','?'))" 2>/dev/null || echo "Grafana: UNREACHABLE"
curl -s --max-time 3 http://localhost:9090/-/healthy || echo "Prometheus: UNREACHABLE"
curl -s --max-time 3 http://localhost:9101/metrics | head -3 || echo "Evidently exporter: UNREACHABLE"
```

**7. Node.js BFF**:
```bash
curl -s --max-time 3 http://localhost:3001/health | python3 -m json.tool 2>/dev/null || echo "UNREACHABLE"
```

**8. Vue frontend**:
```bash
curl -s --max-time 3 http://localhost:5173 | grep -o "<title>.*</title>" || echo "UNREACHABLE"
```

**9. k3s (if deployed)**:
```bash
kubectl get pods -n team-comics --no-headers 2>/dev/null | awk '{print $1, $3}' || echo "k3s: not deployed or not accessible"
```

**10. Redis**:
```bash
docker exec $(docker compose ps -q redis 2>/dev/null) redis-cli ping 2>/dev/null || echo "Redis: UNREACHABLE"
```

Present results as a status table:

| Service | Status | Port | Notes |
|---------|--------|------|-------|
| MLflow | ✅ Running / ❌ Down | 5001 | |
| MinIO | ... | 9001 | |
| PostgreSQL | ... | 5432 | |
| Redis | ... | 6379 | |
| FastAPI | ... | 8000 | |
| Ollama | ... | 11434 | mistral loaded: yes/no |
| Grafana | ... | 3000 | |
| Prometheus | ... | 9090 | |
| BFF | ... | 3001 | |
| Frontend | ... | 5173 | |
| k3s | ... | 8080 | |

End with: which services need to be started and the command to start them.
