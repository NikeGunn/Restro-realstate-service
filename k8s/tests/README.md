# K8s Test Suite

Run this before every push that touches `k8s/` files.

## How to run

```bash
# From your dev machine (Windows):
ssh -i Kribaat.pem ubuntu@43.152.233.234 'python3 -' < k8s/tests/test_cluster.py

# Or copy and run directly on the server:
scp -i Kribaat.pem k8s/tests/test_cluster.py ubuntu@43.152.233.234:/tmp/
ssh -i Kribaat.pem ubuntu@43.152.233.234 'python3 /tmp/test_cluster.py'
```

## What it checks (14 sections, ~70 assertions)

| # | Section | Why it matters |
|---|---------|---------------|
| 1 | ArgoCD sync & health | Confirms Git is the source of truth and selfHeal is on |
| 2 | All pods Running | No crash-loops, no Terminating stuck pods |
| 3 | Image tag consistency | All components on same version, no mixed deploys |
| 4 | Rolling deploy strategies | Zero-downtime: backend/worker/frontend = RollingUpdate maxUnavailable=0 |
| 5 | PreSync migration job | Migrations run before pods update, job completed |
| 6 | Graceful shutdown | preStop hooks + terminationGracePeriod correct per component |
| 7 | Health probes | startup/readiness/liveness configured on every component |
| 8 | Resource limits | Memory requests sized to actual usage (prevents HPA false alarms) |
| 9 | HPA | backend pinned 1/1 (RWO PVC), frontend scales 2-5 with CPU+memory |
| 10 | ConfigMap | ALLOWED_HOSTS=* (required for K8s probe IPs), DEBUG=False, CORS clean |
| 11 | Redis safety | volatile-lru (protects task queue), AOF persistence on |
| 12 | ArgoCD ingress | No dead nginx annotations on Traefik cluster |
| 13 | Live site | kribaat.com + /api/health/ return 200, response < 3s |
| 14 | Replica counts | All deployments at desired replica count |

## Known invariants (do NOT change without updating tests)

- `ALLOWED_HOSTS=*` is intentional — K8s probes hit pod IPs directly, Django has no CIDR support
- `backend-hpa` stays 1/1 until `/app/media` migrates to S3/MinIO
- `celery-beat` stays `Recreate` — multiple instances would double-fire every scheduled task
- Image tag from CI ≠ ArgoCD revision on config-only commits (CI only builds on code changes)
