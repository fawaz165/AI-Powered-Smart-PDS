# Multi-stage / Production Python 3.11 Image for AI-Powered Smart PDS
FROM python:3.11-slim

# Prevent Python from writing .pyc files to disk and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
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

# Generate dataset, train models, and seed database (if artifacts don't exist)
RUN python ml/data/generate_pds_data.py && \
    python ml/train_demand_model.py && \
    python ml/train_anomaly_model.py

# Expose server port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:5000/api/health || exit 1

# Launch production WSGI / server
CMD ["python", "backend/app.py"]
