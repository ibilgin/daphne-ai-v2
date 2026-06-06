"""
JWT Auth Middleware — Sketch to Story platform, Phase 5.

Roles and permitted routes:
  parent   POST /api/generate-comic, GET /api/comics/{id}, GET /api/jobs/{id}
  admin    GET /api/audit, GET /api/jobs (all), GET /api/comics (all)
  platform POST /internal/*, GET /internal/*, POST /hooks/*

Security rules:
  - Token comparison uses hmac.compare_digest() — never plain ==
  - HTTP 401 for missing/invalid token
  - HTTP 403 for valid token with wrong role
  - JWT secret read from JWT_SECRET env var (populated by Vault at runtime)
  - create_token() is guarded by ENABLE_TOKEN_CREATION env flag (dev/test only)
"""

from __future__ import annotations

import hmac
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Algorithm and token bearer scheme
# ---------------------------------------------------------------------------
_ALGORITHM = "HS256"
_bearer_scheme = HTTPBearer(auto_error=False)

# ---------------------------------------------------------------------------
# Role → allowed route prefixes
# ---------------------------------------------------------------------------
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "parent": [
        "POST /api/generate-comic",
        "GET /api/comics/",
        "GET /api/jobs/",
    ],
    "admin": [
        "GET /api/audit",
        "GET /api/jobs",
        "GET /api/comics",
    ],
    "platform": [
        "POST /internal/",
        "GET /internal/",
        "POST /hooks/",
    ],
}


# ---------------------------------------------------------------------------
# TokenPayload
# ---------------------------------------------------------------------------

class TokenPayload:
    """Parsed JWT payload returned by decode_token()."""

    def __init__(self, user_id: str, role: str, exp: datetime) -> None:
        self.user_id = user_id
        self.role = role
        self.exp = exp

    def __repr__(self) -> str:
        return f"TokenPayload(user_id={self.user_id!r}, role={self.role!r})"


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def _get_jwt_secret() -> str:
    """Read JWT_SECRET from env — never hardcode."""
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        raise RuntimeError(
            "JWT_SECRET environment variable is not set. "
            "Ensure Vault has injected it before starting the API."
        )
    return secret


def decode_token(token: str) -> TokenPayload:
    """
    Validate a JWT and return the parsed payload.

    Raises
    ------
    HTTPException 401 — if the token is missing, malformed, expired, or uses
    an unexpected algorithm.
    """
    try:
        import jwt as pyjwt

        secret = _get_jwt_secret()
        payload: dict[str, Any] = pyjwt.decode(
            token,
            secret,
            algorithms=[_ALGORITHM],
        )
    except ImportError:
        # Fallback: try python-jose
        try:
            from jose import JWTError, jwt as jose_jwt

            secret = _get_jwt_secret()
            try:
                payload = jose_jwt.decode(token, secret, algorithms=[_ALGORITHM])
            except JWTError as exc:
                logger.warning("decode_token: jose JWTError — %s", exc)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token.",
                    headers={"WWW-Authenticate": "Bearer"},
                ) from exc
        except ImportError as import_exc:
            raise RuntimeError(
                "Neither PyJWT nor python-jose is installed. "
                "Add PyJWT or python-jose[cryptography] to requirements.txt."
            ) from import_exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("decode_token: invalid token — %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user_id = payload.get("sub", "")
    role = payload.get("role", "")
    exp_ts = payload.get("exp")

    if not user_id or not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing 'sub' or 'role'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    exp_dt = (
        datetime.fromtimestamp(exp_ts, tz=timezone.utc)
        if exp_ts is not None
        else datetime.now(tz=timezone.utc)
    )
    return TokenPayload(user_id=user_id, role=role, exp=exp_dt)


def require_role(role: str):
    """
    FastAPI dependency factory that enforces a required role.

    Usage::

        @app.get("/api/audit")
        async def get_audit(payload: TokenPayload = Depends(require_role("admin"))):
            ...

    Returns
    -------
    A FastAPI ``Depends()`` callable.

    Raises
    ------
    HTTP 401 — token missing or invalid.
    HTTP 403 — token is valid but the role does not match ``role``.
    """

    def _check(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    ) -> TokenPayload:
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing Bearer token.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = credentials.credentials
        payload = decode_token(token)

        # Use hmac.compare_digest to prevent timing-based attacks
        if not hmac.compare_digest(payload.role, role):
            logger.warning(
                "require_role: role mismatch — required=%r got=%r user_id=%s",
                role,
                payload.role,
                payload.user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' required; token has role '{payload.role}'.",
            )

        return payload

    return Depends(_check)


def create_token(
    user_id: str,
    role: str,
    secret: str,
    expires_hours: int = 24,
) -> str:
    """
    Create a signed JWT for local testing.

    This function is guarded: it raises RuntimeError if the
    ENABLE_TOKEN_CREATION env var is not set to "1" or "true".
    Never use in production — secrets must come from Vault.
    """
    flag = os.environ.get("ENABLE_TOKEN_CREATION", "").lower()
    if flag not in {"1", "true", "yes"}:
        raise RuntimeError(
            "create_token() is disabled in production. "
            "Set ENABLE_TOKEN_CREATION=true to use this in local dev/test only."
        )

    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(hours=expires_hours),
    }

    try:
        import jwt as pyjwt

        return pyjwt.encode(payload, secret, algorithm=_ALGORITHM)
    except ImportError:
        pass

    try:
        from jose import jwt as jose_jwt

        return jose_jwt.encode(payload, secret, algorithm=_ALGORITHM)
    except ImportError as exc:
        raise RuntimeError(
            "Neither PyJWT nor python-jose is installed."
        ) from exc
