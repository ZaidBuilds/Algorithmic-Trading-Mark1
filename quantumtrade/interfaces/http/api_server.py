from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from quantumtrade.backtesting.walk_forward import rolling_walk_forward
from quantumtrade.interfaces.http.auth import JWTAuth, JWTAuthError
from quantumtrade.interfaces.http.routes.strategies import router as strategies_router
from quantumtrade.interfaces.http.routes.risk import router as risk_router
from quantumtrade.interfaces.websocket.ws_server import notify_job_update

app = FastAPI(title="QuantumTrade API", version="0.8.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

jwt_auth = JWTAuth()

app.include_router(strategies_router)
app.include_router(risk_router)


@dataclass
class JobState:
    job_id: str
    status: str  # queued|running|finished|failed|cancelled
    progress: float
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    cancel_event: Optional[threading.Event] = None


_JOB_LOCK = threading.Lock()
_JOBS: Dict[str, JobState] = {}


def _get_job(job_id: str) -> JobState:
    with _JOB_LOCK:
        if job_id not in _JOBS:
            raise KeyError(job_id)
        return _JOBS[job_id]


async def _yield_progress(job_id: str, queue: asyncio.Queue, pct: float, msg: str) -> None:
    await queue.put({"job_id": job_id, "type": "progress", "progress": pct, "message": msg})


def _run_walk_forward_job(
    job_id: str,
    params: Dict[str, Any],
    progress_queue: Optional[asyncio.Queue] = None,
) -> None:
    try:
        with _JOB_LOCK:
            job = _get_job(job_id)
            job.status = "running"
            job.progress = 0.0
            cancel_event = job.cancel_event

        if progress_queue:
            # best-effort: may not be running
            try:
                asyncio.run(_yield_progress(job_id, progress_queue, 0.05, "Loading data"))
            except RuntimeError:
                pass

        # Data payload: expected to provide OHLCV as list of rows
        # request: { "symbol": "...", "data": [{"time":..., "open":..., ...}, ...], "train_bars":..., "test_bars":..., "param_grid":[...], "initial_balance":..., "commission":... }
        rows = params.get("data") or []
        if not rows:
            raise ValueError("Missing request.data (OHLCV rows).")

        df = pd.DataFrame(rows)
        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"], unit="s", errors="coerce")
            df = df.dropna(subset=["time"]).set_index("time")
        else:
            # allow ISO strings
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
                df = df.dropna(subset=["timestamp"]).set_index("timestamp")
            else:
                raise ValueError("data rows must include 'time' (unix seconds) or 'timestamp'.")

        symbol = params.get("symbol", "UNKNOWN")

        # Strategy factory hook:
        # For now, we support "strategy_name" -> instantiation via existing strategies package.
        # This should be replaced with a robust registry later.
        from strategy import get_strategy

        strategy_name = params.get("strategy", "EMA Crossover")
        required_params_factory = params.get("strategy_param_keys", [])  # optional

        param_grid = params.get("param_grid", [])
        if not param_grid:
            raise ValueError("Missing or empty request.param_grid")

        # pick required columns for strategies
        # most strategies expect 'Close' at minimum
        if "Close" not in df.columns and "close" in df.columns:
            df = df.rename(columns={"close": "Close"})
        if "Open" not in df.columns and "open" in df.columns:
            df = df.rename(columns={"open": "Open"})
        if "High" not in df.columns and "high" in df.columns:
            df = df.rename(columns={"high": "High"})
        if "Low" not in df.columns and "low" in df.columns:
            df = df.rename(columns={"low": "Low"})
        if "Volume" not in df.columns and "volume" in df.columns:
            df = df.rename(columns={"volume": "Volume"})

        train_bars = int(params.get("train_bars", 30))
        test_bars = int(params.get("test_bars", 10))
        initial_balance = float(params.get("initial_balance", 10000.0))
        commission = float(params.get("commission", 0.001))

        def strategy_factory(p: Dict[str, Any]):
            cls = get_strategy(strategy_name)
            return cls(**p)

        result = rolling_walk_forward(
            data=df,
            strategy_factory=strategy_factory,
            param_grid=param_grid,
            initial_balance=initial_balance,
            commission=commission,
            train_bars=train_bars,
            test_bars=test_bars,
        )

        with _JOB_LOCK:
            job = _get_job(job_id)
            job.status = "finished"
            job.progress = 1.0
            job.result = {
                "symbol": symbol,
                "walk_forward": result.aggregated,
                "folds": [
                    {
                        "train_start": f.train_start,
                        "train_end": f.train_end,
                        "test_start": f.test_start,
                        "test_end": f.test_end,
                        "best_params": f.best_params,
                        "test_metrics_summary": f.test_metrics_summary,
                    }
                    for f in result.folds
                ],
            }
            result_payload = job.result

        if progress_queue:
            try:
                asyncio.run(_yield_progress(job_id, progress_queue, 1.0, "Done"))
            except RuntimeError:
                pass

        try:
            asyncio.run(notify_job_update(job_id=job_id, status="finished", progress=1.0, result=result_payload))
        except RuntimeError:
            pass

    except Exception as e:
        with _JOB_LOCK:
            job = _get_job(job_id)
            job.status = "failed"
            job.progress = 1.0
            job.error = str(e)

        try:
            asyncio.run(notify_job_update(job_id=job_id, status="failed", progress=1.0))
        except RuntimeError:
            pass


class RESTAuthResponse(JSONResponse):
    def __init__(self, message: str):
        super().__init__(status_code=401, content={"detail": message})


def get_progress_queue(request: Request) -> Optional[asyncio.Queue]:
    # placeholder for future: WS coordination
    return None


@app.get("/health")
def health():
    return {"ok": True, "service": "quantumtrade-api"}


@app.post("/api/jobs/walk-forward")
def create_walk_forward_job(
    req: Dict[str, Any],
    background: BackgroundTasks,
    _: Dict[str, Any] = Depends(jwt_auth.require_jwt),
):
    # Create job + kick in background thread
    job_id = str(uuid.uuid4())
    cancel_event = threading.Event()

    job = JobState(
        job_id=job_id,
        status="queued",
        progress=0.0,
        result=None,
        error=None,
        cancel_event=cancel_event,
    )
    with _JOB_LOCK:
        _JOBS[job_id] = job

    # fire and forget in thread (so FastAPI threadpool doesn't block)
    params = dict(req or {})
    def target():
        _run_walk_forward_job(job_id=job_id, params=params, progress_queue=None)

    t = threading.Thread(target=target, daemon=True)
    t.start()

    return {"job_id": job_id, "status": job.status}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, _: Dict[str, Any] = Depends(jwt_auth.require_jwt)):
    try:
        job = _get_job(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")

    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "result": job.result,
        "error": job.error,
    }
