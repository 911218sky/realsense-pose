# NYCU RealSense Pose

A pose estimation and analysis system using Intel RealSense cameras with MediaPipe.

## Quick Start

### Using Docker (Recommended)

1. Download the latest release from [Releases](../../releases)
2. Extract `realsense-pose_deploy.zip`
3. Copy `env.example` to `.env` and configure as needed
4. Run:
   ```bash
   docker compose up -d
   ```

### Using Pre-built Image

```bash
docker pull ghcr.io/911218sky/realsense-pose:latest
```

## Configuration

Key environment variables in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `API_PORT` | 8100 | API server port |
| `MONGO_ROOT_PASSWORD` | - | MongoDB password |
| `IS_PROD` | 0 | Production mode |

## Development

```bash
# Clone repository
git clone https://github.com/911218sky/realsense-pose.git
cd realsense-pose

# Start with dev profile
docker compose --profile dev up --build -d
```

## Architecture

- FastAPI backend with pose estimation
- MongoDB for data persistence
- Redis for caching
- Flutter Web UI
- Watchtower for auto-updates
- Nginx reverse proxy with rate limiting
- Fail2Ban for DDoS protection

## DDoS Protection

The system includes Nginx + Fail2Ban for DDoS protection.

### Traffic Flow

```
Internet → Nginx (Port 80) → API (Port 8100)
              ↓
         Fail2Ban (monitors Nginx logs)
```

### Protection Mechanisms

#### Nginx Rate Limiting
- 50 requests per second per IP (burst 100)
- 20 concurrent connections per IP
- Blocks common attack paths (`.env`, `.git`, etc.)

#### Fail2Ban Rules

| Rule | Trigger | Ban Duration |
|------|---------|--------------|
| nginx-ddos | 250 requests in 10 seconds | 7 days |
| nginx-limit-req | 10 rate-limit hits in 2 minutes | 2 hours |
| nginx-badbots | Malicious bot detected | 24 hours |
| nginx-botsearch | Scanning sensitive paths | 24 hours |
| nginx-shellshock | Shellshock exploit attempt | 7 days |
| nginx-auth-fail | 10 failed auth (401/403) in 5 min | 24 hours |
| nginx-exploit | SQL injection, XSS, path traversal | 24 hours |
| nginx-noscript | Access .php/.asp/.jsp files | 24 hours |
| nginx-noproxy | Open proxy abuse | 7 days |

### Configuration Files

| File | Purpose |
|------|---------|
| `fail2ban/jail.local` | Main config: ban duration, thresholds, whitelist |
| `fail2ban/filter.d/nginx-ddos.conf` | DDoS filter: high request rate detection |
| `fail2ban/filter.d/nginx-badbots.conf` | Bot filter: scanners (sqlmap, nmap) and sensitive paths |
| `fail2ban/filter.d/nginx-exploit.conf` | Exploit filter: SQL injection, XSS, path traversal |
| `fail2ban/filter.d/nginx-shellshock.conf` | Shellshock exploit detection |
| `fail2ban/filter.d/nginx-auth-fail.conf` | Brute force login detection (401/403) |
| `fail2ban/filter.d/nginx-noscript.conf` | Script file access (.php, .asp, .jsp) |
| `fail2ban/filter.d/nginx-noproxy.conf` | Open proxy abuse detection |
| `nginx/nginx.conf` | Nginx config: rate limiting, proxy settings |

### Fail2Ban Commands

```bash
# Check status
docker exec realsense-pose-fail2ban fail2ban-client status

# Check specific jail
docker exec realsense-pose-fail2ban fail2ban-client status nginx-ddos

# Unban an IP
docker exec realsense-pose-fail2ban fail2ban-client set nginx-ddos unbanip <IP>

# View banned IPs
docker exec realsense-pose-fail2ban fail2ban-client get nginx-ddos banned
```

### Customization

#### Adjust Rate Limit
Edit `nginx/nginx.conf`:
```nginx
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=20r/s;
limit_req zone=api_limit burst=50 nodelay;
```

#### Adjust Ban Rules
Edit `fail2ban/jail.local`:
```ini
[nginx-ddos]
maxretry = 200      # trigger threshold
findtime = 10       # detection window (seconds)
bantime = 7200      # ban duration (seconds)
```

#### Whitelist IPs
Add to `[DEFAULT]` section in `fail2ban/jail.local`:
```ini
ignoreip = 127.0.0.1/8 ::1 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 YOUR_IP
```

### Notes

- Fail2Ban requires Linux host (won't work on Windows Docker Desktop)
- Nginx rate limiting works on all platforms
- Logs are rotated automatically (max 30MB total)