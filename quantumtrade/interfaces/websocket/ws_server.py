from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List, Optional

import jwt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.security import HTTPBearer

WS_APP = FastAPI(title="QuantumTrade WS")

_job_subscribers: Dict[str, List[WebSocket]] = {}


def _get_jwt_secret() -> str:
    secret = os.getenv("API_JWT_SECRET", "")
    if not secret:
        raise RuntimeError("API_JWT_SECRET is not configured")
    return secret


def verify_jwt_token(token: str) -> Dict[str, Any]:
    secret = _get_jwt_secret()
    alg = os.getenv("API_JWT_ALG", "HS256")
    return jwt.decode(token, secret, algorithms=[alg], options={"require": ["exp"]})


async def require_jwt_ws(
    websocket: WebSocket,
    authorization: Optional[str] = None,
) -> Dict[str, Any]:
    # Accept either query param/header Authorization.
    auth_header = authorization
    if auth_header is None:
        auth_header = websocket.headers.get("Authorization")

    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise WebSocketDisconnect(code=status.WS_1008_POLICY_VIOLATION)

    token = auth_header.split(" ", 1)[1].strip()
    try:
        return verify_jwt_token(token)
    except Exception:
        raise WebSocketDisconnect(code=status.WS_1008_POLICY_VIOLATION)


@WS_APP.websocket("/ws")
async def ws_control(websocket: WebSocket):
    await websocket.accept()

    try:
        # Auth gate
        _ = await require_jwt_ws(websocket)

        await websocket.send_json({"type": "hello", "ok": True})
        while True:
            msg = await websocket.receive_text()
            try:
                payload = json.loads(msg)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "invalid json"})
                continue

            # Minimal control protocol (Phase 8–10 scaffold)
            # Expected:
            #   { "type": "ping" } or { "type":"subscribe", "job_id":"..." }
            msg_type = payload.get("type")
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            elif msg_type == "subscribe":
                job_id = payload.get("job_id")
                if job_id:
                    if job_id not in _job_subscribers:
                        _job_subscribers[job_id] = []
                    _job_subscribers[job_id].append(websocket)
                    await websocket.send_json({"type": "subscribed", "job_id": job_id})
                else:
                    await websocket.send_json(
                        {"type": "error", "message": "job_id required for subscribe"}
                    )
            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "WS scaffold: subscribe/control not wired yet",
                    }
                )

    except WebSocketDisconnect:
        for job_id in _job_subscribers:
            _job_subscribers[job_id] = [ws for ws in _job_subscribers[job_id] if ws != websocket]
        return


async def notify_job_update(
    job_id: str, status: str, progress: float, result: Optional[Dict] = None
) -> None:
    subscribers = _job_subscribers.get(job_id, [])
    if not subscribers:
        return

    message = {"type": "job_update", "job_id": job_id, "status": status, "progress": progress}
    if result is not None:
        message["result"] = result

    for ws in subscribers:
        try:
            await ws.send_json(message)
        except Exception:
            pass
