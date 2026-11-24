# ==============================================================================
# FraudGuard Dockerfile: separate frontend and backend runtime image targets
#
#   docker build --target backend-runtime -t fraudguard-backend .
#   docker build --target frontend-runtime -t fraudguard-frontend .
#   docker build --target test -t fraudguard-test .       -> image that runs pytest (used by Jenkins)
# ==============================================================================

# Stage 1: Build the React TypeScript frontend
# (Vite 8 needs Node >= 20.19 or >= 22.12; 22 is what the build was verified with)
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Stage 2: Python base = dependencies + backend code (shared by the test and runtime stages)
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# build-essential and libgomp for LightGBM (OpenMP); curl for the healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

# Backend, models and application code
COPY backend/ ./backend/
COPY artifacts/ ./artifacts/
COPY sim_registry/ ./sim_registry/
COPY features.py policy.py serve.py train.py retrain.py ./

# Git for Windows checks text files out with CRLF line endings. LightGBM on Linux cannot parse a
# CRLF model.txt ("Model format error, expect a tree here", then the process aborts), so normalise to LF.
RUN sed -i 's/\r$//' artifacts/model.txt sim_registry/*/model.txt

# Stage 3: Test target (Jenkins runs this). Not part of the final image.
FROM base AS test
COPY conftest.py demo_rows.json ./
COPY tests/ ./tests/
# Dummy values so the Google-login tests can run in CI without real credentials
ENV GOOGLE_CLIENT_ID=ci-dummy-client-id \
    GOOGLE_CLIENT_SECRET=ci-dummy-secret
CMD ["python", "-m", "pytest", "tests", "-q"]

# Stage 4: Frontend runtime image
FROM nginx:alpine AS frontend-runtime
COPY --from=frontend-builder /app/frontend/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Stage 5: Backend runtime image (keep this LAST so it is the default target)
FROM base AS backend-runtime

# SECRET_KEY is NOT set here on purpose: pass it at run time (docker-compose.yml requires it).
ENV ENVIRONMENT=production \
    MODEL_DIR=artifacts \
    PORT=8000 \
    DB_PATH=/app/data/fraudguard.db

# Run as a non-root user; /app/data holds the SQLite database (mounted as a volume)
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/data \
    && chown -R app:app /app
USER app
VOLUME ["/app/data"]

EXPOSE 8000

# /health returns 200 only once the model has loaded (~30-40 s)
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "8000"]