# RealSense Pose Helm Chart

A Helm chart for deploying RealSense Pose application on Kubernetes.

## Prerequisites

- Kubernetes 1.23+
- Helm 3.8+
- PV provisioner support in the underlying infrastructure (for persistence)

## Installation

### From OCI Registry (Recommended)

```bash
# Install latest version
helm install realsense-pose oci://ghcr.io/911218sky/realsense-pose \
  --set mongodb.auth.rootPassword=YOUR_SECURE_PASSWORD

# Install specific version
helm install realsense-pose oci://ghcr.io/911218sky/realsense-pose --version 1.0.0 \
  --set mongodb.auth.rootPassword=YOUR_SECURE_PASSWORD

# With custom values file
helm install realsense-pose oci://ghcr.io/911218sky/realsense-pose \
  -f values-prod.yaml \
  --set mongodb.auth.rootPassword=YOUR_SECURE_PASSWORD
```

### From Local Chart (Development)

```bash
helm install realsense-pose ./helm/realsense-pose \
  -f ./helm/realsense-pose/values-dev.yaml
```

### Production Deployment

```bash
helm install realsense-pose oci://ghcr.io/911218sky/realsense-pose \
  -f ./helm/realsense-pose/values-prod.yaml \
  --set mongodb.auth.rootPassword=YOUR_SECURE_PASSWORD \
  --set ingress.hosts[0].host=your-domain.com
```

## Uninstallation

```bash
helm uninstall realsense-pose
```

## Configuration

### Global Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `nameOverride` | Override chart name | `""` |
| `fullnameOverride` | Override full name | `""` |
| `imagePullSecrets` | Image pull secrets | `[]` |

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
| `api.corsAllowOrigins` | CORS allowed origins | `""` |
| `api.auth.enabled` | Enable authentication | `false` |
| `api.auth.clientSecrets` | Auth client secrets | `""` |
| `api.resources.limits.cpu` | CPU limit | `1000m` |
| `api.resources.limits.memory` | Memory limit | `2Gi` |
| `api.persistence.data.enabled` | Enable data persistence | `true` |
| `api.persistence.data.size` | Data volume size | `10Gi` |
| `api.persistence.outputs.enabled` | Enable outputs persistence | `true` |
| `api.persistence.outputs.size` | Outputs volume size | `10Gi` |

### Nginx

| Parameter | Description | Default |
|-----------|-------------|---------|
| `nginx.enabled` | Enable Nginx reverse proxy | `true` |
| `nginx.image.repository` | Nginx image | `nginx` |
| `nginx.image.tag` | Nginx tag | `alpine` |
| `nginx.replicaCount` | Number of Nginx replicas | `1` |

### MongoDB

| Parameter | Description | Default |
|-----------|-------------|---------|
| `mongodb.enabled` | Enable MongoDB | `true` |
| `mongodb.image.repository` | MongoDB image | `mongo` |
| `mongodb.image.tag` | MongoDB tag | `8.0` |
| `mongodb.auth.rootPassword` | **REQUIRED** Root password | `""` |
| `mongodb.auth.database` | Database name | `nycu_rehab` |
| `mongodb.persistence.enabled` | Enable persistence | `true` |
| `mongodb.persistence.size` | Volume size | `10Gi` |

### Redis

| Parameter | Description | Default |
|-----------|-------------|---------|
| `redis.enabled` | Enable Redis | `true` |
| `redis.image.repository` | Redis image | `redis` |
| `redis.image.tag` | Redis tag | `8-alpine` |
| `redis.maxmemory` | Max memory | `256mb` |
| `redis.persistence.enabled` | Enable persistence | `true` |
| `redis.persistence.size` | Volume size | `1Gi` |

### Ingress

| Parameter | Description | Default |
|-----------|-------------|---------|
| `ingress.enabled` | Enable Ingress | `false` |
| `ingress.className` | Ingress class | `nginx` |
| `ingress.annotations` | Ingress annotations | `{}` |
| `ingress.hosts` | Ingress hosts | `[{host: realsense-pose.local, paths: [{path: /, pathType: Prefix}]}]` |
| `ingress.tls` | TLS configuration | `[]` |

### Network Policy

| Parameter | Description | Default |
|-----------|-------------|---------|
| `networkPolicy.enabled` | Enable NetworkPolicy | `false` |

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

## Troubleshooting

### Check pod status

```bash
kubectl get pods -l app.kubernetes.io/instance=realsense-pose
```

### View logs

```bash
kubectl logs -l app.kubernetes.io/instance=realsense-pose,app.kubernetes.io/component=api -f
```

### Access MongoDB shell

```bash
kubectl exec -it realsense-pose-mongodb-0 -- mongosh -u root -p
```

## License

MIT
