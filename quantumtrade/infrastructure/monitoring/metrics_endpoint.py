"""Prometheus Metrics HTTP Server.

This module provides a dedicated HTTP endpoint for Prometheus to scrape
metrics. It runs as a separate daemon thread or can be executed as a
standalone script.

Usage:
    # In main application:
    from monitoring.metrics_endpoint import start_metrics_endpoint
    start_metrics_endpoint(port=8000)

    # Or as standalone:
    python -m monitoring.metrics_endpoint --port 8000

Endpoints:
    GET /metrics          - Prometheus metrics exposition format
    GET /health           - Simple health check (200 OK)
    GET /ready            - Readiness check (includes Prometheus registry state)

Environment:
    METRICS_PORT          - Port to bind (default: 8000)
    METRICS_ADDR          - Address to bind (default: 0.0.0.0)
"""

import argparse
import os
import sys
import time
import threading
from typing import Optional

from prometheus_client import start_http_server, REGISTRY, generate_latest
from flask import Flask, jsonify, Response

app = Flask(__name__)

# Track startup time for uptime metric
START_TIME = time.time()


@app.route('/metrics')
def metrics():
    """Prometheus metrics endpoint."""
    return Response(generate_latest(REGISTRY), mimetype='text/plain; version=0.0.4; charset=utf-8')


@app.route('/health')
def health():
    """Liveness probe - returns 200 if process is running."""
    return jsonify({
        'status': 'healthy',
        'timestamp': time.time(),
        'uptime_seconds': time.time() - START_TIME,
    }), 200


@app.route('/ready')
def ready():
    """Readiness probe - returns 200 if app is ready to serve traffic."""
    # Check if core dependencies are accessible
    try:
        # Could add more checks: DB connection, broker connection, etc.
        return jsonify({
            'status': 'ready',
            'timestamp': time.time(),
            'prometheus_registry': 'ok',
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'not_ready',
            'error': str(e),
        }), 503


@app.route('/')
def index():
    """Root endpoint with basic info."""
    return jsonify({
        'app': 'QuantumTrade Metrics',
        'endpoints': {
            'metrics': '/metrics',
            'health': '/health',
            'ready': '/ready',
        },
        'uptime_seconds': time.time() - START_TIME,
    })


def start_metrics_endpoint(
    host: str = "0.0.0.0",
    port: Optional[int] = None,
    flask_kwargs: Optional[dict] = None,
) -> threading.Thread:
    """Start the metrics HTTP server in a background thread.

    Args:
        host: Host address to bind
        port: Port to listen on (default from METRICS_PORT env or 8000)
        flask_kwargs: Additional kwargs for Flask.run()

    Returns:
        Thread object for the server
    """
    if port is None:
        port = int(os.getenv('METRICS_PORT', '8000'))

    def run_flask():
        try:
            app.run(
                host=host,
                port=port,
                debug=False,
                use_reloader=False,
                **(flask_kwargs or {})
            )
        except OSError as e:
            if e.errno == 98:  # Address already in use
                print(f"⚠️  Metrics endpoint already running on {host}:{port}")
            else:
                raise

    thread = threading.Thread(target=run_flask, daemon=True, name="MetricsEndpoint")
    thread.start()
    print(f"✅ Metrics endpoint started on http://{host}:{port}/metrics")
    return thread


def run_standalone():
    """Run metrics endpoint as a standalone script."""
    parser = argparse.ArgumentParser(description="QuantumTrade Prometheus Metrics Endpoint")
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind')
    parser.add_argument('--port', type=int, default=int(os.getenv('METRICS_PORT', '8000')),
                       help='Port to listen on')
    args = parser.parse_args()

    print(f"🚀 Starting metrics endpoint on {args.host}:{args.port}")
    start_metrics_endpoint(host=args.host, port=args.port)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Metrics endpoint stopped")


if __name__ == '__main__':
    run_standalone()
