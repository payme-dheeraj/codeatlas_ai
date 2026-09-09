# 15 — Kubernetes Deployment

## Overview

CodeAtlas AI provides production-grade Kubernetes deployment via Helm charts. All stateless services are horizontally scalable. Stateful services (PostgreSQL, Redis, Qdrant, Neo4j, MinIO) use persistent volumes and StatefulSets.

---

## Helm Chart Structure

```
charts/codeatlas/
├── Chart.yaml
├── values.yaml
├── values-production.yaml
├── templates/
│   ├── _helpers.tpl
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secrets.yaml
│   ├── # Application services
│   ├── auth/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── hpa.yaml
│   ├── repo-service/
│   ├── parser/
│   ├── ai-service/
│   ├── diagram/
│   ├── docs/
│   ├── security/
│   ├── search/
│   ├── worker/
│   ├── frontend/
│   ├── # Infrastructure
│   ├── gateway/
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── ingress.yaml
│   ├── # Monitoring
│   └── monitoring/
│       ├── servicemonitor.yaml
│       └── prometheusrule.yaml
```

---

## values.yaml (excerpt)

```yaml
global:
  image:
    registry: ghcr.io/your-org/codeatlas
    tag: latest
    pullPolicy: IfNotPresent
  namespace: codeatlas

replicaCounts:
  auth: 2
  repoService: 2
  parser: 3          # CPU-intensive
  aiService: 2
  worker: 4          # Scale based on queue depth
  diagram: 1
  docs: 1
  security: 2
  search: 2
  frontend: 2

resources:
  aiService:
    requests:
      cpu: "1"
      memory: "2Gi"
    limits:
      cpu: "4"
      memory: "8Gi"
  parser:
    requests:
      cpu: "500m"
      memory: "1Gi"
    limits:
      cpu: "2"
      memory: "4Gi"
  default:
    requests:
      cpu: "100m"
      memory: "256Mi"
    limits:
      cpu: "500m"
      memory: "512Mi"

autoscaling:
  enabled: true
  worker:
    minReplicas: 2
    maxReplicas: 20
    targetCPUUtilizationPercentage: 70
  parser:
    minReplicas: 2
    maxReplicas: 10
    targetCPUUtilizationPercentage: 80

ingress:
  enabled: true
  className: nginx
  host: codeatlas.your-domain.com
  tls:
    enabled: true
    secretName: codeatlas-tls

postgresql:
  enabled: true           # use bundled chart or set externalUrl
  auth:
    database: codeatlas
    existingSecret: codeatlas-db-secret

redis:
  enabled: true
  auth:
    existingSecret: codeatlas-redis-secret

qdrant:
  enabled: true
  persistence:
    size: 50Gi

neo4j:
  enabled: true
  neo4j:
    password: ""          # from secret
  volumes:
    data:
      size: 50Gi

minio:
  enabled: true
  rootUser: minioadmin
  rootPassword: ""        # from secret
  persistence:
    size: 100Gi

ollama:
  enabled: false          # enable for local LLM
  gpu:
    enabled: true
    type: nvidia
```

---

## Sample Deployment Manifest (AI Service)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ai-service
  namespace: codeatlas
  labels:
    app: ai-service
    version: {{ .Chart.AppVersion }}
spec:
  replicas: {{ .Values.replicaCounts.aiService }}
  selector:
    matchLabels:
      app: ai-service
  template:
    metadata:
      labels:
        app: ai-service
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8004"
        prometheus.io/path: "/metrics"
    spec:
      containers:
        - name: ai-service
          image: {{ .Values.global.image.registry }}/ai-service:{{ .Values.global.image.tag }}
          ports:
            - containerPort: 8004
          env:
            - name: POSTGRES_URL
              valueFrom:
                secretKeyRef:
                  name: codeatlas-db-secret
                  key: url
            - name: REDIS_URL
              valueFrom:
                secretKeyRef:
                  name: codeatlas-redis-secret
                  key: url
            - name: QDRANT_URL
              value: "http://qdrant:6333"
            - name: NEO4J_URL
              value: "bolt://neo4j:7687"
            - name: LLM_PROVIDER
              valueFrom:
                configMapKeyRef:
                  name: codeatlas-config
                  key: llm_provider
            - name: OPENAI_API_KEY
              valueFrom:
                secretKeyRef:
                  name: codeatlas-llm-secret
                  key: openai_api_key
                  optional: true
          resources:
            requests:
              cpu: {{ .Values.resources.aiService.requests.cpu }}
              memory: {{ .Values.resources.aiService.requests.memory }}
            limits:
              cpu: {{ .Values.resources.aiService.limits.cpu }}
              memory: {{ .Values.resources.aiService.limits.memory }}
          livenessProbe:
            httpGet:
              path: /health
              port: 8004
            initialDelaySeconds: 30
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /ready
              port: 8004
            initialDelaySeconds: 10
            periodSeconds: 10
```

---

## Horizontal Pod Autoscaler (Worker)

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: worker-hpa
  namespace: codeatlas
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: worker
  minReplicas: 2
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: External
      external:
        metric:
          name: redis_queue_length
          selector:
            matchLabels:
              queue: celery
        target:
          type: AverageValue
          averageValue: "10"    # Scale up when >10 tasks per pod in queue
```

---

## Ingress Configuration

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: codeatlas-ingress
  namespace: codeatlas
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "100m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "300"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "300"
    nginx.ingress.kubernetes.io/configuration-snippet: |
      proxy_set_header X-Real-IP $remote_addr;
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - codeatlas.your-domain.com
      secretName: codeatlas-tls
  rules:
    - host: codeatlas.your-domain.com
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: gateway
                port:
                  number: 8000
          - path: /
            pathType: Prefix
            backend:
              service:
                name: frontend
                port:
                  number: 3000
```

---

## Deployment Commands

```bash
# Add Helm repos
helm repo add bitnami https://charts.bitnami.com/bitnami

# Install CodeAtlas
helm install codeatlas ./charts/codeatlas \
  --namespace codeatlas \
  --create-namespace \
  --values values-production.yaml \
  --set global.image.tag=v1.2.0

# Upgrade
helm upgrade codeatlas ./charts/codeatlas \
  --namespace codeatlas \
  --values values-production.yaml

# Check status
kubectl get pods -n codeatlas
kubectl get hpa -n codeatlas

# Scale manually
kubectl scale deployment worker --replicas=8 -n codeatlas

# View logs
kubectl logs -n codeatlas -l app=ai-service -f --tail=100
```

---

## Resource Requirements (Production)

| Tier | vCPU | RAM | Storage |
|------|------|-----|---------|
| **Small** (< 10 repos, 10 users) | 8 | 16 GB | 100 GB |
| **Medium** (< 50 repos, 50 users) | 16 | 32 GB | 500 GB |
| **Large** (< 200 repos, 200 users) | 32 | 64 GB | 2 TB |
| **Enterprise** (500+ repos) | 64+ | 128+ GB | 10+ TB |
