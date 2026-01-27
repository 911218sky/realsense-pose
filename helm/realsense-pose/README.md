# RealSense Pose Helm Chart

A Helm chart for deploying RealSense Pose application on Kubernetes.

## Prerequisites

- Kubernetes 1.23+
- Helm 3.8+
- PV provisioner support in the underlying infrastructure (for persistence)

### Install Helm

**Windows (PowerShell)**
```powershell
winget install Helm.Helm --source winget
# Restart terminal after installation
helm version
```

**Linux (Ubuntu/Debian)**
```bash
curl https://baltocdn.com/helm/signing.asc | gpg --dearmor | sudo tee /usr/share/keyrings/helm.gpg > /dev/null
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/helm.gpg] https://baltocdn.com/helm/stable/debian/ all main" | sudo tee /etc/apt/sources.list.d/helm-stable-debian.list
sudo apt-get update
sudo apt-get install helm
```

**macOS**
```bash
brew install helm
```

### Enable Kubernetes

#### Option 1: Docker Desktop (Easiest for Windows/macOS)

1. Open Docker Desktop
2. Settings → Kubernetes → Enable Kubernetes
3. Click "Apply & Restart"
4. Wait for Kubernetes to start

#### Option 2: Minikube (Cross-platform)

**Windows (PowerShell)**
```powershell
# Install Minikube
winget install Kubernetes.minikube

# Start Minikube
minikube start --driver=hyperv  # or --driver=virtualbox

# Verify installation
kubectl get nodes
```

**Linux**
```bash
# Install Minikube
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
sudo install minikube-linux-amd64 /usr/local/bin/minikube

# Start Minikube
minikube start

# Verify installation
kubectl get nodes
```

**macOS**
```bash
# Install Minikube
brew install minikube

# Start Minikube
minikube start

# Verify installation
kubectl get nodes
```

#### Option 3: Kind (Kubernetes in Docker)

**Windows (PowerShell)**
```powershell
# Install Kind
winget install Kubernetes.kind

# Create cluster
kind create cluster --name realsense-pose

# Verify installation
kubectl cluster-info --context kind-realsense-pose
```

**Linux / macOS**
```bash
# Install Kind
# Linux
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.20.0/kind-linux-amd64
chmod +x ./kind
sudo mv ./kind /usr/local/bin/kind

# macOS
brew install kind

# Create cluster
kind create cluster --name realsense-pose

# Verify installation
kubectl cluster-info --context kind-realsense-pose
```

#### Option 4: K3s (Lightweight, Linux only)

```bash
# Install K3s
curl -sfL https://get.k3s.io | sh -

# Set kubeconfig
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# Verify installation
sudo kubectl get nodes
```

#### Option 5: MicroK8s (Ubuntu/Linux)

```bash
# Install MicroK8s
sudo snap install microk8s --classic

# Add user to microk8s group
sudo usermod -a -G microk8s $USER
sudo chown -f -R $USER ~/.kube
newgrp microk8s

# Enable required addons
microk8s enable dns storage

# Set kubectl alias
alias kubectl='microk8s kubectl'

# Verify installation
kubectl get nodes
```

**Note:** For Minikube/Kind, use `service.type=NodePort` instead of `LoadBalancer` in installation commands below.

## Quick Start

### Local Development (Docker Desktop)

**Windows (PowerShell)**
```powershell
# Install with LoadBalancer (recommended for Docker Desktop)
helm install realsense-pose oci://ghcr.io/911218sky/realsense-pose-helm `
  --set mongodb.auth.rootPassword=your-password `
  --set service.type=LoadBalancer

# Access at http://localhost:80
```

**Linux / macOS**
```bash
# Install with LoadBalancer (recommended for Docker Desktop)
helm install realsense-pose oci://ghcr.io/911218sky/realsense-pose-helm \
  --set mongodb.auth.rootPassword=your-password \
  --set service.type=LoadBalancer

# Access at http://localhost:80
```

### Using Port Forward (Alternative)

**Windows (PowerShell)**
```powershell
# Install
helm install realsense-pose oci://ghcr.io/911218sky/realsense-pose-helm `
  --set mongodb.auth.rootPassword=your-password

# Forward port (keep terminal open)
kubectl port-forward svc/realsense-pose-realsense-pose-helm-nginx 8100:80

# Access at http://localhost:8100
```

**Linux / macOS**
```bash
# Install
helm install realsense-pose oci://ghcr.io/911218sky/realsense-pose-helm \
  --set mongodb.auth.rootPassword=your-password

# Forward port (keep terminal open)
kubectl port-forward svc/realsense-pose-realsense-pose-helm-nginx 8100:80

# Access at http://localhost:8100
```

## Installation Options

### From OCI Registry (Recommended)

**Windows (PowerShell)**
```powershell
# Install latest version
helm install realsense-pose oci://ghcr.io/911218sky/realsense-pose-helm `
  --set mongodb.auth.rootPassword=YOUR_SECURE_PASSWORD

# Install specific version
helm install realsense-pose oci://ghcr.io/911218sky/realsense-pose-helm `
  --version 1.0.3 `
  --set mongodb.auth.rootPassword=YOUR_SECURE_PASSWORD
```

**Linux / macOS**
```bash
# Install latest version
helm install realsense-pose oci://ghcr.io/911218sky/realsense-pose-helm \
  --set mongodb.auth.rootPassword=YOUR_SECURE_PASSWORD

# Install specific version
helm install realsense-pose oci://ghcr.io/911218sky/realsense-pose-helm \
  --version 1.0.3 \
  --set mongodb.auth.rootPassword=YOUR_SECURE_PASSWORD
```

### From Local Chart (Development)

**Windows (PowerShell)**
```powershell
helm install realsense-pose ./helm/realsense-pose `
  -f ./helm/realsense-pose/values-dev.yaml
```

**Linux / macOS**
```bash
helm install realsense-pose ./helm/realsense-pose \
  -f ./helm/realsense-pose/values-dev.yaml
```

## Service Types

### LoadBalancer (Docker Desktop / Cloud)

Best for Docker Desktop or cloud environments with LoadBalancer support.

**Windows (PowerShell)**
```powershell
helm install realsense-pose oci://ghcr.io/911218sky/realsense-pose-helm `
  --set mongodb.auth.rootPassword=password `
  --set service.type=LoadBalancer

# Access at http://localhost:80
```

**Linux / macOS**
```bash
helm install realsense-pose oci://ghcr.io/911218sky/realsense-pose-helm \
  --set mongodb.auth.rootPassword=password \
  --set service.type=LoadBalancer

# Access at http://localhost:80
```

### NodePort

Exposes service on a static port on each node.

**Windows (PowerShell)**
```powershell
helm install realsense-pose oci://ghcr.io/911218sky/realsense-pose-helm `
  --set mongodb.auth.rootPassword=password `
  --set service.type=NodePort

# Get the assigned port
kubectl get svc realsense-pose-realsense-pose-helm-nginx

# Access at http://localhost:<NodePort>
```

**Linux / macOS**
```bash
helm install realsense-pose oci://ghcr.io/911218sky/realsense-pose-helm \
  --set mongodb.auth.rootPassword=password \
  --set service.type=NodePort

# Get the assigned port
kubectl get svc realsense-pose-realsense-pose-helm-nginx

# Access at http://localhost:<NodePort>
```

### ClusterIP (Default)

Internal access only, requires port-forward.

```bash
helm install realsense-pose oci://ghcr.io/911218sky/realsense-pose-helm \
  --set mongodb.auth.rootPassword=password

# Port forward to access
kubectl port-forward svc/realsense-pose-realsense-pose-helm-nginx 8100:80
```

## Upgrade & Uninstall

### Upgrade to Latest Version

**Windows (PowerShell)**
```powershell
helm upgrade realsense-pose oci://ghcr.io/911218sky/realsense-pose-helm `
  --set mongodb.auth.rootPassword=password `
  --set service.type=LoadBalancer
```

**Linux / macOS**
```bash
helm upgrade realsense-pose oci://ghcr.io/911218sky/realsense-pose-helm \
  --set mongodb.auth.rootPassword=password \
  --set service.type=LoadBalancer
```

### Uninstall

```bash
helm uninstall realsense-pose

# Also delete PVCs if you want to remove all data
kubectl delete pvc -l app.kubernetes.io/instance=realsense-pose
```

## Production Deployment

**Windows (PowerShell)**
```powershell
helm install realsense-pose oci://ghcr.io/911218sky/realsense-pose-helm `
  -f ./helm/realsense-pose/values-prod.yaml `
  --set mongodb.auth.rootPassword=YOUR_SECURE_PASSWORD `
  --set ingress.enabled=true `
  --set ingress.hosts[0].host=your-domain.com
```

**Linux / macOS**
```bash
helm install realsense-pose oci://ghcr.io/911218sky/realsense-pose-helm \
  -f ./helm/realsense-pose/values-prod.yaml \
  --set mongodb.auth.rootPassword=YOUR_SECURE_PASSWORD \
  --set ingress.enabled=true \
  --set ingress.hosts[0].host=your-domain.com
```

## Configuration

### Global Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `nameOverride` | Override chart name | `""` |
| `fullnameOverride` | Override full name | `""` |
| `imagePullSecrets` | Image pull secrets | `[]` |

### Service

| Parameter | Description | Default |
|-----------|-------------|---------|
| `service.type` | Service type: `ClusterIP`, `NodePort`, `LoadBalancer` | `ClusterIP` |
| `service.port` | Service port | `80` |

### API Service

| Parameter | Description | Default |
|-----------|-------------|---------|
| `api.image.repository` | API image repository | `ghcr.io/911218sky/realsense-pose` |
| `api.image.tag` | API image tag | `latest` |
| `api.replicaCount` | Number of API replicas | `1` |
| `api.port` | API service port | `8100` |
| `api.prefix` | API URL prefix | `/v1` |
| `api.isProd` | Production mode | `"1"` |
| `api.serveWeb` | Serve web UI | `"1"` |
| `api.resources.limits.cpu` | CPU limit | `1000m` |
| `api.resources.limits.memory` | Memory limit | `2Gi` |
| `api.persistence.data.enabled` | Enable data persistence | `true` |
| `api.persistence.data.size` | Data volume size | `10Gi` |

### MongoDB

| Parameter | Description | Default |
|-----------|-------------|---------|
| `mongodb.enabled` | Enable MongoDB | `true` |
| `mongodb.auth.rootPassword` | **REQUIRED** Root password | `""` |
| `mongodb.auth.database` | Database name | `nycu_rehab` |
| `mongodb.persistence.enabled` | Enable persistence | `true` |
| `mongodb.persistence.size` | Volume size | `10Gi` |

### Redis

| Parameter | Description | Default |
|-----------|-------------|---------|
| `redis.enabled` | Enable Redis | `true` |
| `redis.maxmemory` | Max memory | `256mb` |
| `redis.persistence.enabled` | Enable persistence | `true` |
| `redis.persistence.size` | Volume size | `1Gi` |

### Ingress

| Parameter | Description | Default |
|-----------|-------------|---------|
| `ingress.enabled` | Enable Ingress | `false` |
| `ingress.className` | Ingress class | `nginx` |
| `ingress.hosts` | Ingress hosts | See values.yaml |
| `ingress.tls` | TLS configuration | `[]` |

## Common Operations

### Check Status

```bash
# View all pods
kubectl get pods -l app.kubernetes.io/instance=realsense-pose

# View services
kubectl get svc -l app.kubernetes.io/instance=realsense-pose

# View all resources
kubectl get all -l app.kubernetes.io/instance=realsense-pose
```

### View Logs

```bash
# API logs
kubectl logs -l app.kubernetes.io/component=api -f

# Nginx logs
kubectl logs -l app.kubernetes.io/component=nginx -f

# MongoDB logs
kubectl logs -l app.kubernetes.io/component=mongodb -f
```

### Access MongoDB Shell

```bash
kubectl exec -it realsense-pose-realsense-pose-helm-mongodb-0 -- mongosh -u root -p
```

### Restart Deployment

```bash
kubectl rollout restart deployment -l app.kubernetes.io/instance=realsense-pose
```

## Troubleshooting

### Pod not starting

```bash
# Check pod status
kubectl describe pod <pod-name>

# Check events
kubectl get events --sort-by='.lastTimestamp'
```

### 502 Bad Gateway

1. Check if API pod is running: `kubectl get pods`
2. Check API logs: `kubectl logs -l app.kubernetes.io/component=api`
3. Verify service endpoints: `kubectl get endpoints`

### Cannot connect to service

1. For `ClusterIP`: Use port-forward
2. For `LoadBalancer`: Wait for external IP assignment
3. For `NodePort`: Use `kubectl get svc` to find the port

### Database connection issues

```bash
# Check MongoDB pod
kubectl logs -l app.kubernetes.io/component=mongodb

# Verify MongoDB is ready
kubectl exec -it realsense-pose-realsense-pose-helm-mongodb-0 -- mongosh --eval "db.adminCommand('ping')"
```

## Examples

### Enable HTTPS with cert-manager

```yaml
ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
  hosts:
    - host: realsense-pose.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: realsense-pose-tls
      hosts:
        - realsense-pose.example.com
```

### Use External MongoDB

```yaml
mongodb:
  enabled: false

api:
  env:
    mongoUri: "mongodb://user:pass@external-mongo:27017/admin"
```

### Enable Authentication

```yaml
api:
  auth:
    enabled: true
    clientSecrets: "client1=secret1,client2=secret2"
```
