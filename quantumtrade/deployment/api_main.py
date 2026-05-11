"""
QuantumTrade API (Phase 8–10 scaffold)

Run:
  python -m uvicorn quantumtrade.deployment.api_main:app --host 0.0.0.0 --port 8000

JWT:
  - set env var API_JWT_SECRET
  - send Authorization: Bearer <token> on REST requests
"""

from __future__ import annotations

from quantumtrade.interfaces.http.api_server import app  # noqa: F401
