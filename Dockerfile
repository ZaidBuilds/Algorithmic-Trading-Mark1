# TradingBot Service Dockerfile
# Main API service for QuantumTrade

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY quantumtrade /app/quantumtrade
COPY config /app/config
COPY monitoring /app/monitoring
COPY strategy /app/strategy
COPY execution /app/execution
COPY risk /app/risk
COPY backtest /app/backtest
COPY live /app/live
COPY brokers /app/brokers
COPY database /app/database
COPY utils /app/utils
COPY ai /app/ai
COPY ml /app/ml
COPY data /app/data
COPY tests /app/tests

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Expose ports
EXPOSE 8080 8000

# Run API server
CMD ["python", "-m", "quantumtrade.main"]
