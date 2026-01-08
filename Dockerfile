# ============================================
# Stage 1: Python dependencies builder
# ============================================
FROM python:3.11.14-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=0 \
    UV_LINK_MODE=copy

WORKDIR /app

ARG CLEAN_VENV=0

# Copy uv binary directly
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files for dependency resolution
COPY pyproject.toml uv.lock .python-version README.md ./

# Create venv and install dependencies using pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /opt/venv \
 && UV_PROJECT_ENVIRONMENT=/opt/venv uv sync --frozen --no-dev --extra db --extra pose \
 && uv pip install "opencv-python-headless>=4.8,<5" --python /opt/venv/bin/python \
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

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY --from=web-downloader /web ./web
COPY scripts/web/precompress_web.py ./scripts/web/precompress_web.py

RUN uv pip install --system --no-cache brotli \
 && python ./scripts/web/precompress_web.py --web-dir ./web

# ============================================
# Stage 4: Final runtime image
# ============================================
FROM python:3.11.14-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Runtime deps for opencv/mediapipe/realsense + ffmpeg (includes libx264 for H.264)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
      libgl1 libglib2.0-0 libusb-1.0-0 ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# Copy venv from builder (changes only when pyproject.toml changes)
COPY --from=builder /opt/venv /opt/venv

# Copy static config files (rarely changes)
COPY configs ./configs

# Copy web UI (changes when frontend releases - separate layer for better cache)
COPY --from=web-compressor /app/web ./web

# Copy source code (changes most frequently - put last for optimal cache hits)
COPY src ./src

EXPOSE 8100

# Default: run API server inside container
CMD ["uvicorn", "api.main:app", "--app-dir", "./src", "--host", "0.0.0.0", "--port", "8100"]
