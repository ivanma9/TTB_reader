# Target platform: linux/amd64 (paddlepaddle wheels require x86_64).
# Build natively on x86_64 or use `docker build --platform linux/amd64`.
FROM python:3.11-slim

# System libraries required by PaddleOCR/OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    libgomp1 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cache model weights in a known path inside the image
ENV PADDLEOCR_HOME=/app/.paddleocr

# Install base package + web extras; httpx needed for smoke_verify.py
COPY pyproject.toml .
RUN pip install --no-cache-dir ".[web]" httpx

# Install PaddlePaddle (CPU x86_64) and PaddleOCR 2.x stable API
RUN pip install --no-cache-dir "paddlepaddle>=2.6.0" && \
    pip install --no-cache-dir "paddleocr>=2.7.0,<3.0.0"

# Bootstrap model weights at build time so the image is immutable and the
# runtime container never depends on a live download from Baidu's CDN.
# Build on a real x86_64 host (Render, GitHub Actions, any Linux CI) so QEMU
# does not need to emulate AVX2. If you are iterating locally on arm64 and
# only need the app to boot, pass --build-arg ALLOW_MISSING_MODELS=true.
ARG ALLOW_MISSING_MODELS=false
COPY scripts/bootstrap_models.py scripts/bootstrap_models.py
RUN python scripts/bootstrap_models.py \
    || ( [ "$ALLOW_MISSING_MODELS" = "true" ] \
         && echo "[WARN] bootstrap skipped — arm64/QEMU build, weights will download at first request" \
         || ( echo "[FATAL] model bootstrap failed; refuse to ship an image that needs runtime downloads" && exit 1 ) )

# Copy remaining source
COPY . .

# Point the eval harness at the real verifier
ENV ALC_EVAL_TARGET=alc_label_verifier.adapter:target

EXPOSE 8000

# Shell form so ${PORT} expands at runtime. Railway/Fly/most PaaS inject PORT;
# local and Render default to 8000 via the fallback.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
