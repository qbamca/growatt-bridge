FROM python:3.12-slim

# Install curl for the healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer-cached unless requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the bridge package itself
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir --no-deps -e .

# Copy skill and reference docs into the image
COPY skill/ skill/
COPY docs/references/ docs/references/

# Audit log directory (mounted as a volume in production)
RUN mkdir -p /var/log/growatt-bridge

# Non-root user
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app /var/log/growatt-bridge
USER appuser

EXPOSE 8081

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8081/health || exit 1

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["uvicorn", "growatt_bridge.main:app", "--host", "0.0.0.0", "--port", "8081"]
