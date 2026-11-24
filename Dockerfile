# ==============================================================================
# FraudGuard Production Dockerfile
# Builds unified React frontend + FastAPI / LightGBM Python backend
# ==============================================================================

# Stage 1: Build the React TypeScript frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Stage 2: Final Python runtime
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies (build-essential and libgomp for LightGBM OpenMP)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend, models, and application code
COPY backend/ ./backend/
COPY artifacts/ ./artifacts/
COPY sim_registry/ ./sim_registry/
COPY features.py policy.py serve.py train.py retrain.py ./

# Copy built frontend assets into frontend/dist
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Expose standard production port
EXPOSE 8000

ENV ENVIRONMENT=production \
    MODEL_DIR=artifacts \
    PORT=8000

# Health check using the Kubernetes readiness probe endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "8000"]
