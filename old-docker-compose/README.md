# 📦 Old Docker Compose Files - Archive

**These files were used for the old deployment method and are no longer needed for production.**

All production deployments now use **Kubernetes with GitOps (ArgoCD)** for zero-downtime deployments.

## Files in This Folder

| File | Original Purpose | Status |
|------|------------------|--------|
| `docker-compose.yml` | Development environment | ⚠️ Archived (use K8s for dev too) |
| `docker-compose.prod.yml` | Old production deployment | ✅ Replaced by Kubernetes |
| `deploy.ps1` | PowerShell deploy script | ✅ Replaced by GitHub Actions |
| `redeploy.ps1` | Quick redeploy script | ✅ Replaced by `git push` |
| `quick-fix.ps1` | Emergency fix script | ✅ No longer needed |
| `build-frontend-direct.ps1` | Frontend build script | ✅ CI/CD handles this now |
| `deploy-ssl.ps1` | SSL certificate setup | ✅ cert-manager handles this |
| `migrate.ps1` | Database migration script | ✅ Auto-migrates on deploy |
| `migrate-to-k8s.ps1` | One-time K8s migration | ✅ Already completed |
| `migrate-k8s-simple.ps1` | One-time K8s migration | ✅ Already completed |

## Why These Were Archived

### Old Deployment (Docker Compose)
- **Downtime**: 3-8 minutes per deployment
- **Manual Process**: SSH + run scripts manually
- **No Rollback**: Hard to revert bad deployments
- **No Autoscaling**: Fixed number of containers
- **Single Server**: Can't scale horizontally

### New Deployment (Kubernetes + GitOps)
- **Zero Downtime**: ✅ Rolling updates
- **Automated**: ✅ Just `git push`
- **Easy Rollback**: ✅ `kubectl rollout undo`
- **Autoscaling**: ✅ HPA scales based on load
- **Multi-Server**: ✅ Can add nodes

## If You Need to Use Docker Compose Again

If you need to run the old Docker Compose setup for testing or development:

```bash
# Go to project root
cd "C:\Users\Nautilus\Desktop\RESTRO\Restro & real estate"

# Use the archived files
docker-compose -f old-docker-compose/docker-compose.yml up -d
```

**Note**: This is NOT recommended for production. Use Kubernetes instead.

## Current Production Setup

See these files for current deployment:
- **Deployment Guide**: [HOW_TO_DEPLOY_GUIDE.md](../HOW_TO_DEPLOY_GUIDE.md)
- **K8s Manifests**: [k8s/](../k8s/)
- **CI/CD Pipeline**: [.github/workflows/deploy.yml](../.github/workflows/deploy.yml)

---

**Archived Date**: January 22, 2026  
**Reason**: Migrated to Kubernetes for zero-downtime deployments
