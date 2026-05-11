"""FastAPI model serving server."""

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import asyncio
import logging
from datetime import datetime
import sys

sys.path.append("D:/zaidsystem/02_Coding/Projects/algotrading/tradingbotv1")

from quantumtrade.mlops.registry import ModelRegistry
from quantumtrade.mlops.serving.predictor import Predictor, PredictionRequest, BatchPredictionRequest
from quantumtrade.mlops.serving.versioning import ModelVersionManager

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="QuantumTrade Model Serving",
    description="ML model serving API for QuantumTrade trading bot",
    version="1.0.0",
)

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: datetime
    model_count: int
    ready: bool


class ModelListResponse(BaseModel):
    """Response for model listing."""
    models: List[Dict[str, Any]]


class ModelVersionListResponse(BaseModel):
    """Response for version listing."""
    name: str
    versions: List[Dict[str, Any]]


class PromoteRequest(BaseModel):
    """Request to promote model version."""
    version: str = Field(..., description="Version to promote")
    stage: str = Field(..., description="Target stage: staging|production|archived")


# Global instances (initialized on startup)
registry: Optional[ModelRegistry] = None
predictor: Optional[Predictor] = None
version_manager: Optional[ModelVersionManager] = None


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    global registry, predictor, version_manager
    
    logger.info("Starting model serving server...")
    
    # Initialize registry
    registry = ModelRegistry()
    
    # Initialize predictor
    predictor = Predictor(registry)
    
    # Initialize version manager
    version_manager = ModelVersionManager(registry)
    
    logger.info("Model serving server ready")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down model server")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    model_count = 0
    try:
        models = registry.list_models() if registry else []
        model_count = len(models)
    except:
        pass
    
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        model_count=model_count,
        ready=predictor is not None,
    )


@app.get("/models", response_model=ModelListResponse)
async def list_models():
    """List all registered models."""
    try:
        models = registry.list_models()
        model_list = []
        for m in models:
            latest_prod = m.get_latest_version("Production")
            latest_staging = m.get_latest_version("Staging")
            model_list.append({
                "name": m.name,
                "latest_production": latest_prod.version if latest_prod else None,
                "latest_staging": latest_staging.version if latest_staging else None,
                "created_at": m.creation_timestamp.isoformat(),
            })
        return ModelListResponse(models=model_list)
    except Exception as e:
        logger.error(f"Failed to list models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/models/{model_name}/versions", response_model=ModelVersionListResponse)
async def list_versions(model_name: str):
    """List all versions of a model."""
    try:
        versions = registry.list_versions(model_name)
        version_list = [
            {
                "version": v.version,
                "stage": v.stage,
                "metrics": v.metrics,
                "run_id": v.run_id,
            }
            for v in versions
        ]
        return ModelVersionListResponse(name=model_name, versions=version_list)
    except Exception as e:
        logger.error(f"Failed to list versions: {e}")
        raise HTTPException(status_code=404, detail=f"Model {model_name} not found")


@app.post("/predict/{model_name}")
async def predict(
    model_name: str,
    request: PredictionRequest,
    background_tasks: BackgroundTasks,
):
    """
    Single prediction endpoint.
    
    Returns model prediction with confidence.
    """
    try:
        result = await predictor.predict(
            model_name=model_name,
            features=request.features,
            version=request.version,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        raise HTTPException(status_code=500, detail="Prediction failed")


@app.post("/predict/batch/{model_name}")
async def batch_predict(
    model_name: str,
    request: BatchPredictionRequest,
    background_tasks: BackgroundTasks,
):
    """Batch prediction endpoint."""
    try:
        results = []
        for features in request.features_list:
            result = await predictor.predict(
                model_name=model_name,
                features=features,
                version=request.version,
            )
            results.append(result)
        return {"predictions": results}
    except Exception as e:
        logger.error(f"Batch prediction failed: {e}")
        raise HTTPException(status_code=500, detail="Batch prediction failed")


@app.post("/models/{model_name}/promote/{version}")
async def promote_model(
    model_name: str,
    version: str,
    promote_request: PromoteRequest,
):
    """
    Promote model version to stage.
    
    Stages: None -> Staging -> Production -> Archived
    """
    try:
        registry.promote_model(model_name, version, promote_request.stage)
        return {
            "status": "success",
            "model": model_name,
            "version": version,
            "stage": promote_request.stage,
        }
    except Exception as e:
        logger.error(f"Promotion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/models/{model_name}/latest/{stage}")
async def get_latest_model(model_name: str, stage: str = "production"):
    """Get latest model version in given stage."""
    try:
        version = registry.get_latest_model(model_name, stage=stage)
        if version is None:
            raise HTTPException(
                status_code=404,
                detail=f"No {stage} model found for {model_name}"
            )
        return version.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/models/{model_name}/rollback/{version}")
async def rollback_model(model_name: str, version: str):
    """Rollback to previous model version."""
    try:
        registry.rollback_model(model_name, version)
        return {
            "status": "success",
            "model": model_name,
            "rolled_back_to": version,
        }
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics")
async def get_metrics():
    """Get server metrics."""
    try:
        if predictor:
            predictor_metrics = predictor.get_metrics()
        else:
            predictor_metrics = {}
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "predictor": predictor_metrics,
            "cache_hits": predictor.cache_hits if predictor else 0,
            "cache_misses": predictor.cache_misses if predictor else 0,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/cache")
async def clear_cache():
    """Clear prediction cache."""
    try:
        if predictor:
            predictor.clear_cache()
        return {"status": "cache_cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
