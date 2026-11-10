# Multi-stage / Production Python 3.11 Image for AI-Powered Smart PDS
FROM python:3.11-slim

# Prevent Python from writing .pyc files to disk and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PORT=5000
ENV FLASK_ENV=production
ENV MONGO_URI=mongodb://mongo:27017/smart_pds_db
ENV DB_NAME=smart_pds_db

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY backend/requirements.txt /app/backend/
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy application source code
COPY . /app/

# Generate dataset, train models, and serialize artifacts
RUN python backend/ml/data/generate_pds_data.py && \
    python backend/ml/train_demand_model.py && \
    python backend/ml/train_anomaly_model.py

# Create non-root system user and configure file permissions
RUN useradd -m -u 10001 -s /bin/bash pdsuser && \
    chown -R pdsuser:pdsuser /app

# Switch to non-root execution
USER pdsuser

# Expose server port
EXPOSE 5000

# Health check using installed curl targeting dynamic ${PORT:-5000}
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:${PORT:-5000}/api/health || exit 1

# Launch production WSGI server with Gunicorn (1 worker, 2 threads for Render memory optimization)
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 1 --threads 2 --timeout 120 backend.app:app"]
