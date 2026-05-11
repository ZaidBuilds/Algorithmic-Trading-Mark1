# Model Serving Service Dockerfile
# FastAPI-based inference server for QuantumTrade ML models

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY quantumtrade /app/quantumtrade
COPY config /app/config

# Expose port
EXPOSE 8001

# Run server
CMD ["uvicorn", "quantumtrade.mlops.serving.server:app", "--host", "0.0.0.0", "--port", "8001"]
