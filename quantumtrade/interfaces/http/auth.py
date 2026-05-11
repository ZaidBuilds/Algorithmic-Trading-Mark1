from __future__ import annotations

import os
from typing import Any, Dict, Optional

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


class JWTAuthError(Exception):
    pass


class JWTAuth:
    """Minimal HS256 JWT auth helper for FastAPI.

    Expected header:
      Authorization: Bearer <token>

    Config:
      API_JWT_SECRET (required)
      API_JWT_ALG (optional, default HS256)
    """

    def __init__(
        self,
        *,
        secret: Optional[str] = None,
        algorithm: str = "HS256",
        audience: Optional[str] = None,
        issuer: Optional[str] = None,
    ):
        self.secret = (secret or os.getenv("API_JWT_SECRET", "")).strip()
        self.algorithm = os.getenv("API_JWT_ALG", algorithm)

        # optional claims validation
        self.audience = audience or os.getenv("API_JWT_AUDIENCE")
        self.issuer = issuer or os.getenv("API_JWT_ISSUER")

        self.bearer = HTTPBearer(auto_error=False)

        # Allow API to import even if JWT is not configured (useful for dev/health checks).
        # Endpoints that require JWT will still reject requests if disabled.
        self.jwt_enabled = bool(self.secret)

    def verify_token(self, token: str) -> Dict[str, Any]:
        # Read secret/alg dynamically to avoid env mismatches between process
        # startup and runtime in some dev/test environments.
        secret = (os.getenv("API_JWT_SECRET") or self.secret).strip()
        if not secret:
            raise JWTAuthError("JWT auth is not configured (API_JWT_SECRET missing).")

        # If env is missing/invalid, fall back to HS256 (the expected default).
        alg = os.getenv("API_JWT_ALG") or self.algorithm
        if alg not in {"HS256", "HS384", "HS512"}:
            alg = "HS256"

        # Debug (safe): do not log secret itself.
        try:
            header_alg = jwt.get_unverified_header(token).get("alg")
        except Exception:
            header_alg = None

        # secret length lets us confirm which secret is used
        # (helps identify env mismatches between uvicorn restarts).
        print(f"[JWTAuth] secret_len={len(secret)} expected_alg={alg} token_header_alg={header_alg}")

        options = {"require": ["exp"]}
        kwargs: Dict[str, Any] = {
            "key": secret,
            "algorithms": [alg],
            "options": options,
        }

        if self.audience:
            kwargs["audience"] = self.audience
        if self.issuer:
            kwargs["issuer"] = self.issuer

        try:
            payload = jwt.decode(token, **kwargs)
        except jwt.PyJWTError as e:
            raise JWTAuthError(str(e)) from e

        return payload

    async def require_jwt(
        self, authorization: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False))
    ) -> Dict[str, Any]:
        if not self.jwt_enabled:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="JWT auth is not configured (API_JWT_SECRET missing).",
            )

        if authorization is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing Authorization header",
            )
        if authorization.scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid auth scheme",
            )

        try:
            return self.verify_token(authorization.credentials)
        except JWTAuthError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Unauthorized: {e}",
            )
