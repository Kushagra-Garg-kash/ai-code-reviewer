# ---- Base image ----
# Slim variant: smaller image, faster pulls, still has apt available
# for bandit/pylint's needs (they're pure Python, so no extra system deps required).
FROM python:3.11-slim

# ---- Environment setup ----
# Prevents Python from writing .pyc files and buffers stdout/stderr,
# which keeps container logs (docker logs) showing output immediately.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ---- Working directory ----
WORKDIR /app

# ---- Dependency installation (cached layer) ----
# Copy requirements.txt BEFORE the rest of the code. Docker caches layers,
# so if only your source code changes (not dependencies), this layer is reused
# and rebuilds are much faster.
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ---- Copy application code ----
# Everything else: main.py, app/, and anything else needed at runtime.
# .dockerignore (see below) keeps venv, .env, __pycache__, tests, etc. out of the image.
COPY . .

# ---- Expose port ----
# FastAPI/uvicorn default. Render (Week 4 Day 2) will map its own port to this.
EXPOSE 8000

# ---- Run the app ----
# No --reload in production/container context — reload is a dev-only feature
# that watches the filesystem for changes, which you don't want in a built image.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]