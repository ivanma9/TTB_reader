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

# Bootstrap model weights at build time.
# On QEMU-emulated ARM64 this step may fail (AVX2 not emulated);
# models will be downloaded automatically on first use in that case.
COPY scripts/bootstrap_models.py scripts/bootstrap_models.py
RUN python scripts/bootstrap_models.py || echo "[WARN] bootstrap skipped - models will download on first run"

# Copy remaining source
COPY . .

# Point the eval harness at the real verifier
ENV ALC_EVAL_TARGET=alc_label_verifier.adapter:target

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
