# ============================================
# Stage 1: Python dependencies builder
# ============================================
FROM python:3.11.14-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

ARG CLEAN_VENV=0

# Copy uv binary directly (skip pip install = faster)
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv

RUN python -m venv /opt/venv

COPY requirements.txt requirements_db.txt requirements_pose.txt ./

# Install all deps in ONE uv call = faster resolution
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --no-compile -r requirements_db.txt -r requirements.txt -r requirements_pose.txt "opencv-python-headless>=4.8,<5" \
 && if [ "$CLEAN_VENV" = "1" ]; then \
      find /opt/venv -type d \( -name "__pycache__" -o -name "tests" \) -exec rm -rf {} + 2>/dev/null || true; \
    fi

# ============================================
# Stage 2: Download web UI from latest release
# ============================================
FROM alpine:3.20 AS web-downloader

RUN apk add --no-cache curl jq unzip

WORKDIR /web

RUN DOWNLOAD_URL=$(curl -sf https://api.github.com/repos/911218sky/gait-charts/releases/latest \
      | jq -r '.assets[] | select(.name | startswith("GaitCharts-Web-")) | .browser_download_url') \
 && echo "Downloading: $DOWNLOAD_URL" \
 && curl -fL -o web.zip "$DOWNLOAD_URL" \
 && unzip web.zip -d . \
 && rm web.zip

# ============================================
# Stage 3: Precompress web assets
# ============================================
FROM python:3.11.14-slim-bookworm AS web-compressor

WORKDIR /app

COPY --from=web-downloader /web ./web
COPY scripts/web/precompress_web.py ./scripts/web/precompress_web.py

RUN pip install --no-cache-dir brotli \
 && python ./scripts/web/precompress_web.py --web-dir ./web

# ============================================
# Stage 4: Final runtime image
# ============================================
FROM python:3.11.14-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Runtime deps for opencv/mediapipe/realsense
RUN --mount=type=cache,target=/var/cache/apt \
    apt-get update && apt-get install -y --no-install-recommends \
      libgl1 libglib2.0-0 libusb-1.0-0 \
 && rm -rf /var/lib/apt/lists/*

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv

# Copy static files (least frequently changed first)
COPY configs ./configs
COPY --from=web-compressor /app/web ./web

# Copy source code (most frequently changed last for better cache)
COPY src ./src

EXPOSE 8100

# Default: run API server inside container
CMD ["uvicorn", "api.main:app", "--app-dir", "./src", "--host", "0.0.0.0", "--port", "8100"]
