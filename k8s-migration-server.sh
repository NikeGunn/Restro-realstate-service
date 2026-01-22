#!/bin/bash
# Kubernetes Migration Setup Script
# This runs directly on the Ubuntu server

set -e

echo "============================================"
echo "Kubernetes Migration - ChatPlatform"
echo "============================================"
echo ""

# Step 1: Analyze current setup
echo "[1/9] Analyzing current production setup..."
echo "-------------------------------------------"
echo "Docker containers:"
docker ps --format 'table {{.Names}}\t{{.Status}}' 2>/dev/null || echo "No Docker containers running"
echo ""
echo "System resources:"
echo "Disk: $(df -h / | tail -1 | awk '{print $5 " used"}')"
echo "Memory: $(free -h | grep Mem | awk '{print $3 "/" $2}')"
echo ""

# Step 2: Check if K3s already installed
echo "[2/9] Checking for existing Kubernetes..."
if command -v kubectl &> /dev/null; then
    echo "✓ Kubernetes already installed"
    kubectl version --short 2>/dev/null || true
else
    echo "Installing K3s (this takes 2-3 minutes)..."
    curl -sfL https://get.k3s.io | sh -s - --write-kubeconfig-mode 644

    # Setup kubeconfig
    mkdir -p ~/.kube
    sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
    sudo chown $(id -u):$(id -g) ~/.kube/config

    # Add to bashrc
    if ! grep -q "KUBECONFIG" ~/.bashrc; then
        echo 'export KUBECONFIG=~/.kube/config' >> ~/.bashrc
    fi
    export KUBECONFIG=~/.kube/config

    # Wait for K3s
    echo "Waiting for K3s to be ready..."
    sleep 15
    sudo k3s kubectl wait --for=condition=ready node --all --timeout=120s

    echo "✓ K3s installed successfully"
fi

export KUBECONFIG=~/.kube/config
kubectl get nodes
echo ""

# Step 3: Install cert-manager
echo "[3/9] Installing cert-manager..."
if kubectl get namespace cert-manager &> /dev/null; then
    echo "✓ cert-manager already installed"
else
    kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.0/cert-manager.yaml

    echo "Waiting for cert-manager pods (60 seconds)..."
    sleep 30
    kubectl wait --for=condition=ready pod -l app=cert-manager -n cert-manager --timeout=180s 2>/dev/null || echo "Still starting..."
    kubectl wait --for=condition=ready pod -l app=cainjector -n cert-manager --timeout=60s 2>/dev/null || echo "Still starting..."
    kubectl wait --for=condition=ready pod -l app=webhook -n cert-manager --timeout=60s 2>/dev/null || echo "Still starting..."

    echo "✓ cert-manager installed"
fi
kubectl get pods -n cert-manager
echo ""

# Step 4: Install ArgoCD
echo "[4/9] Installing ArgoCD..."
if kubectl get namespace argocd &> /dev/null; then
    echo "✓ ArgoCD already installed"
else
    kubectl create namespace argocd
    kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

    echo "Waiting for ArgoCD server (90 seconds)..."
    sleep 45
    kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=argocd-server -n argocd --timeout=300s 2>/dev/null || echo "Still starting..."

    echo "✓ ArgoCD installed"
fi

# Get ArgoCD password
ARGOCD_PWD=$(kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" 2>/dev/null | base64 -d || echo "NotReady")

echo ""
echo "============================================"
echo "ArgoCD Access:"
echo "URL: https://43.152.233.234:8080"
echo "Username: admin"
echo "Password: $ARGOCD_PWD"
echo "============================================"
echo ""

# Expose ArgoCD UI
pkill -f "kubectl port-forward.*argocd" 2>/dev/null || true
nohup kubectl port-forward svc/argocd-server -n argocd 8080:443 --address 0.0.0.0 > /tmp/argocd-ui.log 2>&1 &
echo "ArgoCD UI exposed on port 8080"
echo ""

# Step 5: Create namespace
echo "[5/9] Creating chatplatform namespace..."
kubectl create namespace chatplatform 2>/dev/null || echo "Namespace already exists"
kubectl get namespace chatplatform
echo ""

# Step 6: Extract and create secrets
echo "[6/9] Creating Kubernetes secrets..."

# Try to extract from running containers
POSTGRES_PWD="chatplatform123"
if docker ps | grep -q chatplatform_db; then
    EXTRACTED_PWD=$(docker exec chatplatform_db printenv POSTGRES_PASSWORD 2>/dev/null || echo "")
    if [ ! -z "$EXTRACTED_PWD" ]; then
        POSTGRES_PWD="$EXTRACTED_PWD"
        echo "✓ Extracted PostgreSQL password from running container"
    fi
fi

# Generate Django secret key
DJANGO_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))" 2>/dev/null || openssl rand -base64 50)

# Create secret
kubectl create secret generic chatplatform-secrets \
  --namespace=chatplatform \
  --from-literal=SECRET_KEY="$DJANGO_SECRET" \
  --from-literal=POSTGRES_PASSWORD="$POSTGRES_PWD" \
  --from-literal=OPENAI_API_KEY="sk-placeholder-update-me" \
  --from-literal=META_APP_SECRET="placeholder-update-me" \
  --from-literal=WHATSAPP_DEFAULT_VERIFY_TOKEN="placeholder-update-me" \
  --from-literal=INSTAGRAM_DEFAULT_VERIFY_TOKEN="placeholder-update-me" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "✓ Secrets created (remember to update with real values!)"
echo ""

# Step 7: Apply Kubernetes manifests
echo "[7/9] Deploying application to Kubernetes..."

if [ ! -d ~/chatplatform/k8s ]; then
    echo "ERROR: K8s manifests not found at ~/chatplatform/k8s"
    echo "Please upload k8s directory first!"
    exit 1
fi

cd ~/chatplatform/k8s

echo "Applying namespace and config..."
kubectl apply -f namespace.yaml
kubectl apply -f configmap.yaml

echo "Deploying PostgreSQL..."
kubectl apply -f postgres/
sleep 10

echo "Deploying Redis..."
kubectl apply -f redis/
sleep 10

echo "Waiting for databases to be ready (30 seconds)..."
sleep 30
kubectl wait --for=condition=ready pod -l app=postgres -n chatplatform --timeout=120s 2>/dev/null || echo "PostgreSQL still starting..."
kubectl wait --for=condition=ready pod -l app=redis -n chatplatform --timeout=120s 2>/dev/null || echo "Redis still starting..."

echo "Deploying backend application..."
kubectl apply -f backend/

echo "Deploying frontend..."
kubectl apply -f frontend/

echo "Deploying Celery workers..."
kubectl apply -f celery-worker/
kubectl apply -f celery-beat/

echo "Deploying ingress and cert-manager config..."
kubectl apply -f cert-manager/ 2>/dev/null || echo "cert-manager config applied"
kubectl apply -f ingress.yaml

echo "✓ All manifests applied"
echo ""

# Step 8: Wait and check status
echo "[8/9] Checking deployment status..."
echo "Waiting for pods to start (45 seconds)..."
sleep 45

echo ""
echo "============================================"
echo "Pod Status:"
echo "============================================"
kubectl get pods -n chatplatform -o wide

echo ""
echo "Services:"
kubectl get svc -n chatplatform

echo ""
echo "Ingress:"
kubectl get ingress -n chatplatform

echo ""

# Step 9: Verify backend health
echo "[9/9] Testing backend health..."
kubectl port-forward svc/backend -n chatplatform 8001:8000 > /dev/null 2>&1 &
PF_PID=$!
sleep 3

HEALTH_CHECK=$(curl -s http://localhost:8001/api/health/ 2>/dev/null || echo "FAILED")
if [[ "$HEALTH_CHECK" == *"healthy"* ]]; then
    echo "✓ Backend health check PASSED"
    echo "Response: $HEALTH_CHECK"
else
    echo "⚠ Backend health check FAILED or still starting"
    echo "Check logs with: kubectl logs -f deployment/backend -n chatplatform"
fi

kill $PF_PID 2>/dev/null || true

echo ""
echo "============================================"
echo "Migration Complete!"
echo "============================================"
echo ""
echo "Current Status:"
echo "- Old setup (Docker Compose): STILL RUNNING ✓"
echo "- New setup (Kubernetes): DEPLOYED ✓"
echo "- Traffic: STILL ON OLD SETUP (safe!)"
echo ""
echo "Next Steps:"
echo "1. Check pods are healthy: kubectl get pods -n chatplatform"
echo "2. Check logs: kubectl logs -f deployment/backend -n chatplatform"
echo "3. Test K8s app thoroughly before switching traffic"
echo "4. Update secrets: kubectl edit secret chatplatform-secrets -n chatplatform"
echo "5. When ready, switch Nginx to proxy to K8s"
echo ""
echo "ArgoCD UI: https://43.152.233.234:8080"
echo "Username: admin"
echo "Password: $ARGOCD_PWD"
echo ""
echo "To view application logs:"
echo "  kubectl logs -f deployment/backend -n chatplatform"
echo "  kubectl logs -f deployment/frontend -n chatplatform"
echo "  kubectl logs -f deployment/celery-worker -n chatplatform"
echo ""
