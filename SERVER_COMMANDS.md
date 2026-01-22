# 🔧 Quick Server Commands Reference

## ✅ Apply ArgoCD Application (One-Time Setup)

```bash
# SSH to server
ssh -i "Kribaat.pem" ubuntu@43.152.233.234

# Apply ArgoCD application (correct path!)
kubectl apply -f ~/chatplatform/k8s/argocd/application.yaml

# Verify it was created
kubectl get application -n argocd

# Check sync status
kubectl get application chatplatform -n argocd -o wide
```

**Expected Output**:
```
NAME           SYNC STATUS   HEALTH STATUS
chatplatform   Synced        Healthy
```

---

## 📊 Check Deployment Status

```bash
# View all pods
kubectl get pods -n chatplatform

# Watch pods in real-time
watch kubectl get pods -n chatplatform

# Check deployment rollout
kubectl rollout status deployment/backend -n chatplatform
kubectl rollout status deployment/frontend -n chatplatform

# View recent events
kubectl get events -n chatplatform --sort-by='.lastTimestamp' | tail -20
```

---

## 📝 View Logs

```bash
# Backend logs
kubectl logs -f deployment/backend -n chatplatform --tail=100

# Frontend logs
kubectl logs -f deployment/frontend -n chatplatform --tail=50

# Celery worker logs
kubectl logs -f deployment/celery-worker -n chatplatform --tail=100

# All pods with label
kubectl logs -f -l app=backend -n chatplatform --tail=50
```

---

## 🔄 Manual Operations

### Restart Deployments
```bash
# Restart backend (picks up new config, images, etc.)
kubectl rollout restart deployment/backend -n chatplatform

# Restart frontend
kubectl rollout restart deployment/frontend -n chatplatform

# Restart celery workers
kubectl rollout restart deployment/celery-worker -n chatplatform
kubectl rollout restart deployment/celery-beat -n chatplatform

# Restart all
kubectl rollout restart deployment -n chatplatform
```

### Scale Manually
```bash
# Scale backend to 5 replicas
kubectl scale deployment backend --replicas=5 -n chatplatform

# Scale frontend to 3 replicas
kubectl scale deployment frontend --replicas=3 -n chatplatform
```

### Rollback Bad Deployment
```bash
# Rollback backend to previous version
kubectl rollout undo deployment/backend -n chatplatform

# Rollback to specific revision
kubectl rollout history deployment/backend -n chatplatform
kubectl rollout undo deployment/backend --to-revision=2 -n chatplatform
```

---

## 🗄️ Database Operations

```bash
# Connect to PostgreSQL
kubectl exec -it postgres-0 -n chatplatform -- psql -U chatplatform -d chatplatform

# Run Django migrations manually
kubectl exec -it deployment/backend -n chatplatform -- python manage.py migrate

# Django shell
kubectl exec -it deployment/backend -n chatplatform -- python manage.py shell

# Create superuser
kubectl exec -it deployment/backend -n chatplatform -- python manage.py createsuperuser

# Database backup
kubectl exec postgres-0 -n chatplatform -- pg_dump -U chatplatform chatplatform > backup-$(date +%Y%m%d).sql

# Restore database
kubectl exec -i postgres-0 -n chatplatform -- psql -U chatplatform -d chatplatform < backup.sql
```

---

## 🔍 Troubleshooting

### Check Pod Details
```bash
# Describe pod (see events and errors)
kubectl describe pod <pod-name> -n chatplatform

# Get pod YAML
kubectl get pod <pod-name> -n chatplatform -o yaml

# Check resource usage
kubectl top pods -n chatplatform
kubectl top nodes
```

### Check Service Endpoints
```bash
# List services
kubectl get svc -n chatplatform

# Check service endpoints
kubectl get endpoints -n chatplatform

# Test internal connectivity
kubectl exec -it deployment/frontend -n chatplatform -- curl http://backend:8000/admin/
```

### Check Ingress
```bash
# View ingress
kubectl get ingress -n chatplatform

# Describe ingress (see backend mapping)
kubectl describe ingress chatplatform -n chatplatform

# Check Traefik logs
kubectl logs -n kube-system deployment/traefik --tail=100
```

### Check ConfigMap and Secrets
```bash
# View ConfigMap
kubectl get configmap chatplatform-config -n chatplatform -o yaml

# View Secret (base64 encoded)
kubectl get secret chatplatform-secrets -n chatplatform -o yaml

# Decode secret value
kubectl get secret chatplatform-secrets -n chatplatform -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d
```

---

## 🔧 ArgoCD Operations

### Check ArgoCD Status
```bash
# List applications
kubectl get application -n argocd

# Check sync status
kubectl get application chatplatform -n argocd -o yaml | grep -A 10 status

# Describe application
kubectl describe application chatplatform -n argocd
```

### Force ArgoCD Sync
```bash
# Force refresh (hard refresh)
kubectl patch application chatplatform -n argocd --type merge \
  -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}'

# Or use ArgoCD CLI (if installed)
argocd app sync chatplatform
```

### Access ArgoCD UI
```bash
# Get admin password
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d

# Port-forward to access UI
kubectl port-forward svc/argocd-server -n argocd 8080:443

# Then open: https://localhost:8080
# Username: admin
# Password: (from command above)
```

---

## 📦 Docker Operations (Old System - Still Running as Backup)

```bash
# View running Docker Compose containers
cd ~/chatplatform
docker-compose -f docker-compose.prod.yml ps

# View logs
docker-compose -f docker-compose.prod.yml logs -f backend

# Stop Docker Compose (after K8s is stable for 7 days)
docker-compose -f docker-compose.prod.yml down

# Backup Docker Compose database before stopping
docker exec chatplatform_db pg_dump -U chatplatform chatplatform > docker-backup-final.sql
```

---

## 🌐 Network & SSL

### Check Nginx
```bash
# Test nginx config
sudo nginx -t

# Reload nginx
sudo systemctl reload nginx

# View nginx logs
sudo tail -f /var/log/nginx/kribaat-k8s-access.log
sudo tail -f /var/log/nginx/kribaat-k8s-error.log
```

### Check Certificates
```bash
# View cert-manager certificates
kubectl get certificate -n chatplatform

# Check certificate details
kubectl describe certificate chatplatform-tls -n chatplatform

# View cert-manager logs
kubectl logs -n cert-manager deployment/cert-manager --tail=100
```

### Test Site
```bash
# Test from server
curl -I https://kribaat.com

# Test specific endpoint
curl https://kribaat.com/api/health/

# Test backend directly
curl http://localhost:8000/admin/
```

---

## 📊 Monitoring

### Real-time Pod Watching
```bash
# Watch pods update
watch kubectl get pods -n chatplatform

# Watch with timestamps
watch "kubectl get pods -n chatplatform; echo ''; date"

# Watch HPA (autoscaling)
watch kubectl get hpa -n chatplatform
```

### Check Autoscaling
```bash
# View HPA status
kubectl get hpa -n chatplatform

# Describe HPA
kubectl describe hpa backend-hpa -n chatplatform

# View metrics
kubectl top pods -n chatplatform
```

---

## 🚨 Emergency Commands

### Quick Restart Everything
```bash
kubectl rollout restart deployment -n chatplatform
```

### Delete Stuck Pod
```bash
kubectl delete pod <pod-name> -n chatplatform --force --grace-period=0
```

### Switch Back to Docker Compose (Emergency Only!)
```bash
# Update Nginx to point to Docker Compose
sudo nano /etc/nginx/sites-enabled/chatplatform-k8s.conf
# Change proxy_pass to http://localhost:8000

sudo systemctl reload nginx
```

---

## 📁 File Locations on Server

```
~/chatplatform/               # Main project directory
  ├── k8s/                    # Kubernetes manifests
  │   ├── argocd/
  │   │   └── application.yaml  ← ArgoCD app config
  │   ├── backend/
  │   ├── frontend/
  │   └── ...
  ├── backend/               # Django backend code
  ├── frontend/              # React frontend code
  └── docker-compose.prod.yml  # Old Docker Compose (backup)

/etc/nginx/sites-enabled/
  └── chatplatform-k8s.conf   # Nginx config (proxy to K8s)

/var/log/nginx/
  ├── kribaat-k8s-access.log  # Access logs
  └── kribaat-k8s-error.log   # Error logs
```

---

## 🎯 Common Workflows

### Deploy New Code (Automatic)
1. Push code to GitHub: `git push origin main`
2. Wait 7-8 minutes
3. Check: `kubectl rollout status deployment/backend -n chatplatform`

### Update Environment Variables
1. Edit ConfigMap: `kubectl edit configmap chatplatform-config -n chatplatform`
2. Restart pods: `kubectl rollout restart deployment/backend -n chatplatform`

### Check Why Deployment Failed
1. View pod events: `kubectl describe pod <pod-name> -n chatplatform`
2. Check logs: `kubectl logs <pod-name> -n chatplatform`
3. Check GitHub Actions: https://github.com/NikeGunn/Restro-realstate-service/actions

### Rollback Bad Deployment
1. Check history: `kubectl rollout history deployment/backend -n chatplatform`
2. Rollback: `kubectl rollout undo deployment/backend -n chatplatform`
3. Verify: `kubectl get pods -n chatplatform`

---

**Last Updated**: January 22, 2026
**Server**: ubuntu@43.152.233.234
**Cluster**: K3s (Kubernetes)
**Domain**: kribaat.com
