# 🚀 Kubernetes Beginner Guide for Kribaat.com

This guide covers everything you need to manage your Kubernetes deployment on a daily basis.

## 📋 Quick Reference

| What | Command |
|------|---------|
| **SSH to Server** | `ssh -i Kribaat.pem ubuntu@43.152.233.234` |
| **Check all pods** | `sudo k3s kubectl get pods -n chatplatform` |
| **Check logs** | `sudo k3s kubectl logs <pod-name> -n chatplatform` |
| **Restart deployment** | `sudo k3s kubectl rollout restart deployment <name> -n chatplatform` |
| **View ArgoCD** | `https://argocd.kribaat.com` (admin / JZRg2GeoHwg7Y8HL) |

---

## 🔑 Access Your Server

```powershell
# From PowerShell on your Windows machine
ssh -i 'C:\Users\Nautilus\Desktop\RESTRO\Restro & real estate\Kribaat.pem' ubuntu@43.152.233.234
```

Once connected, all kubectl commands should start with `sudo k3s kubectl`.

---

## 🔍 Daily Monitoring Commands

### 1. Check Pod Health
```bash
# List all pods in your namespace
sudo k3s kubectl get pods -n chatplatform

# Check pods with more details (CPU/Memory)
sudo k3s kubectl top pods -n chatplatform

# Watch pods in real-time (press Ctrl+C to exit)
sudo k3s kubectl get pods -n chatplatform -w
```

**Pod Status Meanings:**
| Status | Meaning |
|--------|---------|
| ✅ Running | Pod is healthy and working |
| 🔄 ContainerCreating | Pod is starting up |
| ⚠️ Pending | Waiting for resources |
| ❌ CrashLoopBackOff | Pod keeps crashing (check logs!) |
| 🚫 ImagePullBackOff | Can't download Docker image |

### 2. Check Services & Endpoints
```bash
# List all services
sudo k3s kubectl get svc -n chatplatform

# Check if ingress is working
sudo k3s kubectl get ingress -n chatplatform
```

### 3. View Logs
```bash
# View logs for a specific pod
sudo k3s kubectl logs <pod-name> -n chatplatform

# View last 100 lines
sudo k3s kubectl logs <pod-name> -n chatplatform --tail=100

# Follow logs in real-time (like tail -f)
sudo k3s kubectl logs <pod-name> -n chatplatform -f

# View logs for a crashed/previous container
sudo k3s kubectl logs <pod-name> -n chatplatform --previous

# View logs from all pods of a deployment
sudo k3s kubectl logs -l app=backend -n chatplatform --tail=50
```

---

## 🛠️ Common Troubleshooting

### Problem: Pod is CrashLoopBackOff
```bash
# Step 1: Check the logs
sudo k3s kubectl logs <pod-name> -n chatplatform

# Step 2: Check events
sudo k3s kubectl describe pod <pod-name> -n chatplatform | tail -30

# Step 3: Check previous logs (if it crashed)
sudo k3s kubectl logs <pod-name> -n chatplatform --previous
```

### Problem: Site is Down
```bash
# Step 1: Check if pods are running
sudo k3s kubectl get pods -n chatplatform

# Step 2: Check if services are up
sudo k3s kubectl get svc -n chatplatform

# Step 3: Check ingress
sudo k3s kubectl get ingress -n chatplatform

# Step 4: Check backend health directly
sudo k3s kubectl exec -it <backend-pod> -n chatplatform -- curl -s localhost:8000/api/health/
```

### Problem: Database Connection Failed
```bash
# Step 1: Check if postgres is running
sudo k3s kubectl get pods -n chatplatform | grep postgres

# Step 2: Test postgres connection
sudo k3s kubectl exec -it postgres-0 -n chatplatform -- psql -U chatplatform -d chatplatform -c "SELECT 1;"

# Step 3: Check postgres logs
sudo k3s kubectl logs postgres-0 -n chatplatform
```

---

## 🔄 Deployment & Updates

### Restart a Deployment (Zero Downtime)
```bash
# Restart backend pods one by one
sudo k3s kubectl rollout restart deployment backend -n chatplatform

# Restart frontend
sudo k3s kubectl rollout restart deployment frontend -n chatplatform

# Restart all deployments
sudo k3s kubectl rollout restart deployment -n chatplatform
```

### Check Deployment Status
```bash
# See rollout status
sudo k3s kubectl rollout status deployment backend -n chatplatform

# See deployment history
sudo k3s kubectl rollout history deployment backend -n chatplatform

# Undo last deployment (rollback)
sudo k3s kubectl rollout undo deployment backend -n chatplatform
```

### Scale Pods Up/Down
```bash
# Scale to 3 backend replicas
sudo k3s kubectl scale deployment backend -n chatplatform --replicas=3

# Scale down to 1 replica
sudo k3s kubectl scale deployment backend -n chatplatform --replicas=1

# Check current replica counts
sudo k3s kubectl get deployments -n chatplatform
```

---

## 🗄️ Database Operations

### Access PostgreSQL
```bash
# Connect to PostgreSQL shell
sudo k3s kubectl exec -it postgres-0 -n chatplatform -- psql -U chatplatform -d chatplatform

# Run a SQL query directly
sudo k3s kubectl exec postgres-0 -n chatplatform -- psql -U chatplatform -d chatplatform -c "SELECT COUNT(*) FROM auth_user;"

# Backup database
sudo k3s kubectl exec postgres-0 -n chatplatform -- pg_dump -U chatplatform chatplatform > backup.sql

# Restore database
cat backup.sql | sudo k3s kubectl exec -i postgres-0 -n chatplatform -- psql -U chatplatform chatplatform
```

### Access Redis
```bash
# Connect to Redis CLI
sudo k3s kubectl exec -it redis-0 -n chatplatform -- redis-cli

# Check Redis info
sudo k3s kubectl exec redis-0 -n chatplatform -- redis-cli INFO
```

---

## 🔐 Managing Secrets & Config

### View ConfigMap Values
```bash
# View entire configmap
sudo k3s kubectl get configmap chatplatform-config -n chatplatform -o yaml

# View specific value
sudo k3s kubectl get configmap chatplatform-config -n chatplatform -o jsonpath='{.data.ALLOWED_HOSTS}'
```

### Update ConfigMap
```bash
# Edit configmap interactively
sudo k3s kubectl edit configmap chatplatform-config -n chatplatform

# After editing, restart deployments to pick up changes
sudo k3s kubectl rollout restart deployment backend celery-worker celery-beat -n chatplatform
```

### View Secrets (be careful!)
```bash
# List secrets
sudo k3s kubectl get secrets -n chatplatform

# Decode a secret value
sudo k3s kubectl get secret chatplatform-secrets -n chatplatform -o jsonpath='{.data.SECRET_KEY}' | base64 -d
```

---

## 🌐 ArgoCD - GitOps Deployment

### Access ArgoCD UI
- **URL:** https://argocd.kribaat.com
- **Username:** admin
- **Password:** JZRg2GeoHwg7Y8HL

### ArgoCD CLI Commands
```bash
# Check application status
sudo k3s kubectl get applications -n argocd

# Trigger manual sync
sudo k3s kubectl patch application chatplatform -n argocd -p '{"operation":{"initiatedBy":{"username":"admin"},"sync":{}}}' --type=merge

# Check sync status
sudo k3s kubectl get application chatplatform -n argocd -o jsonpath='{.status.sync.status}'
```

---

## 📊 Resource Monitoring

### Check Resource Usage
```bash
# CPU and Memory of all pods
sudo k3s kubectl top pods -n chatplatform

# CPU and Memory of nodes
sudo k3s kubectl top nodes

# Detailed resource info for a pod
sudo k3s kubectl describe pod <pod-name> -n chatplatform | grep -A5 "Limits\|Requests"
```

### Check HPA (Auto-scaling)
```bash
# View horizontal pod autoscalers
sudo k3s kubectl get hpa -n chatplatform

# Describe HPA to see scaling decisions
sudo k3s kubectl describe hpa backend-hpa -n chatplatform
```

---

## 🧹 Cleanup & Maintenance

### Delete Stuck Pods
```bash
# Force delete a pod
sudo k3s kubectl delete pod <pod-name> -n chatplatform --force --grace-period=0

# Delete all pods (they will recreate)
sudo k3s kubectl delete pods --all -n chatplatform
```

### Clear Old ReplicaSets
```bash
# View old replicasets
sudo k3s kubectl get replicasets -n chatplatform

# Delete replicasets with 0 replicas
sudo k3s kubectl delete replicaset -n chatplatform --field-selector=status.replicas=0
```

### View Cluster Events
```bash
# All events in namespace
sudo k3s kubectl get events -n chatplatform --sort-by='.lastTimestamp'

# Watch events in real-time
sudo k3s kubectl get events -n chatplatform -w
```

---

## 🚨 Emergency Commands

### Quick Health Check
```bash
# One-liner to check everything
sudo k3s kubectl get pods,svc,deployments,hpa -n chatplatform
```

### Emergency Restart
```bash
# Restart everything (nuclear option)
sudo k3s kubectl rollout restart deployment --all -n chatplatform
```

### Check if Site is Working
```bash
# From server
curl -s -o /dev/null -w "%{http_code}" https://kribaat.com

# Response code 200 = OK
```

### View All Resources
```bash
# Everything in namespace
sudo k3s kubectl get all -n chatplatform
```

---

## 📱 Useful Aliases (Add to ~/.bashrc)

```bash
# Add these to your ~/.bashrc on the server
alias k='sudo k3s kubectl'
alias kp='sudo k3s kubectl get pods -n chatplatform'
alias kl='sudo k3s kubectl logs -n chatplatform'
alias kr='sudo k3s kubectl rollout restart deployment -n chatplatform'
alias ke='sudo k3s kubectl get events -n chatplatform --sort-by=.lastTimestamp'

# After adding, run: source ~/.bashrc
```

---

## 🎯 CI/CD Workflow

1. **You make code changes** → Push to GitHub
2. **GitHub Actions** → Builds Docker images, pushes to Docker Hub
3. **ArgoCD** → Detects changes, deploys to Kubernetes
4. **Zero Downtime** → Old pods stay running until new ones are healthy

### Manually Trigger Deployment
Just push to GitHub's `main` branch:
```powershell
# From your local machine
git add .
git commit -m "Your changes"
git push origin main
```

The pipeline will automatically:
1. Build new Docker images
2. Tag them with git commit hash
3. Push to Docker Hub
4. Update k8s/kustomization.yaml with new tag
5. ArgoCD syncs the changes

---

## 📚 Key Information

| Item | Value |
|------|-------|
| Server IP | 43.152.233.234 |
| Domain | kribaat.com |
| Namespace | chatplatform |
| ArgoCD URL | https://argocd.kribaat.com |
| ArgoCD User | admin |
| ArgoCD Pass | JZRg2GeoHwg7Y8HL |
| Docker Hub | nemo2092/chatplatform-* |
| GitHub Repo | NikeGunn/Restro-realstate-service |

---

## 💡 Best Practices

1. **Always check logs first** when something is wrong
2. **Use rollout restart** instead of deleting pods
3. **Never edit running pods** - change deployments/configmaps instead
4. **Backup database** before major changes
5. **Test in staging** before production (if available)
6. **Monitor resource usage** regularly
7. **Keep secrets secure** - never commit them to git

---

Need help? Check:
1. Pod logs: `sudo k3s kubectl logs <pod> -n chatplatform`
2. Events: `sudo k3s kubectl get events -n chatplatform`
3. ArgoCD: https://argocd.kribaat.com
