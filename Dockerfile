# Rodent Study Planner — container image for Google Cloud Run
FROM python:3.11-slim

# Runtime libs some scientific wheels (rdkit) may link against
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxrender1 libxext6 libsm6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code (models, templates, static, etc.)
COPY . .

# Cloud Run injects $PORT (default 8080). gunicorn binds to it.
ENV PORT=8080
EXPOSE 8080

# 1 worker + threads keeps memory low (rdkit/sklearn are heavy) while still
# handling the app's I/O-bound external API calls concurrently.
CMD exec gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 120
