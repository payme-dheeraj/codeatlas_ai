"""FastAPI dependency functions shared across all endpoint modules."""

import uuid
from collections.abc import AsyncGenerator, Callable
from typing import Any

from fastapi import Depends, HTTPException, Query, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.core.redis import RedisCache, get_redis
from app.services.repo_service import RepoService

logger = get_logger(__name__)
_bearer = HTTPBearer(auto_error=False)
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_repo_service(
    session: AsyncSession = Depends(get_db),
) -> RepoService:
    """Provide a RepoService instance bound to the request-scoped DB session.

    Args:
        session: Injected async database session.

    Returns:
        Configured RepoService.
    """
    return RepoService(session)


async def get_cache(
    redis=Depends(get_redis),
) -> RedisCache:
    """Provide a RedisCache helper for the current request.

    Args:
        redis: Injected async Redis client.

    Returns:
        RedisCache wrapper.
    """
    return RedisCache(redis)


async def get_optional_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    api_key: str | None = Security(_api_key_header),
    session: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> uuid.UUID | None:
    """Resolve the current user UUID, or None if unauthenticated.

    This dependency is *optional* only when ``settings.auth_required`` is
    False — in that mode endpoints work for both authenticated and anonymous
    callers.  With the default (``auth_required=True``) it behaves exactly
    like ``get_current_user_id`` and rejects anonymous requests with 401.

    Args:
        credentials: HTTP Bearer token from the Authorization header.
        api_key: Optional raw API key from X-API-Key header.
        session: Injected DB session (used for API key lookup).
        redis: Injected Redis client.

    Returns:
        Decoded user UUID, or None if no valid token is present and
        anonymous access is allowed.
    """
    if settings.auth_required:
        return await get_current_user_id(credentials, api_key, session, redis)

    if credentials is not None:
        try:
            payload = jwt.decode(
                credentials.credentials,
                settings.secret_key,
                algorithms=[settings.jwt_algorithm],
            )
            sub: str | None = payload.get("sub")
            return uuid.UUID(sub) if sub else None
        except (JWTError, ValueError):
            return None

    if api_key is not None:
        from app.services.auth_service import AuthService

        user = await AuthService(session, redis).authenticate_api_key(api_key)
        return user.id if user is not None else None

    return None


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    api_key: str | None = Security(_api_key_header),
    session: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> uuid.UUID:
    """Resolve the current user UUID from a JWT Bearer token or API key.

    Tries Bearer JWT first; falls back to ``X-API-Key`` header.
    Raises HTTP 401 if neither is present or valid.

    Args:
        credentials: Optional HTTP Bearer token.
        api_key: Optional raw API key from X-API-Key header.
        session: Injected DB session (used for API key lookup).
        redis: Injected Redis client (used for token validation).

    Returns:
        Decoded user UUID.

    Raises:
        HTTPException 401: If no valid credential is provided.
    """
    # ── Try JWT Bearer ────────────────────────────────────────────────────────
    if credentials is not None:
        try:
            payload = jwt.decode(
                credentials.credentials,
                settings.secret_key,
                algorithms=[settings.jwt_algorithm],
            )
            sub: str | None = payload.get("sub")
            if sub is None:
                raise JWTError("Missing sub claim.")
            return uuid.UUID(sub)
        except JWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token validation failed: {exc}",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    # ── Try API key ───────────────────────────────────────────────────────────
    if api_key is not None:
        from app.services.auth_service import AuthService

        auth_svc = AuthService(session, redis)
        user = await auth_svc.authenticate_api_key(api_key)
        if user is not None:
            return user.id
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key.",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_authenticated(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    api_key: str | None = Security(_api_key_header),
    token: str | None = Query(default=None, include_in_schema=False),
    session: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> uuid.UUID | None:
    """Router-level authentication gate for all non-public API routes.

    Accepts a Bearer JWT, an ``X-API-Key`` header, or — for Server-Sent
    Events clients that cannot set headers — a ``token`` query parameter.
    When ``settings.auth_required`` is False the gate is a no-op.

    Returns:
        Authenticated user UUID, or None when anonymous access is allowed.

    Raises:
        HTTPException 401: If authentication is required and no valid
        credential is present.
    """
    if not settings.auth_required:
        return None
    if credentials is None and token:
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    return await get_current_user_id(credentials, api_key, session, redis)


async def get_diagram_service(
    session: AsyncSession = Depends(get_db),
) -> "DiagramService":  # type: ignore[name-defined]
    """Provide a DiagramService instance for the current request.

    Args:
        session: Injected async database session.

    Returns:
        Configured DiagramService instance.
    """
    from app.services.diagram_service import DiagramService

    return DiagramService(session)


async def get_document_service(
    session: AsyncSession = Depends(get_db),
) -> "DocumentService":  # type: ignore[name-defined]
    """Provide a DocumentService instance for the current request.

    Args:
        session: Injected async database session.

    Returns:
        Configured DocumentService instance.
    """
    from app.services.document_service import DocumentService

    return DocumentService(session)


async def get_security_service(
    session: AsyncSession = Depends(get_db),
) -> "SecurityService":  # type: ignore[name-defined]
    """Provide a SecurityService instance for the current request.

    Args:
        session: Injected async database session.

    Returns:
        Configured SecurityService instance.
    """
    from app.services.security_service import SecurityService

    return SecurityService(session)


async def get_search_service(
    session: AsyncSession = Depends(get_db),
) -> "SearchService":  # type: ignore[name-defined]
    """Provide a SearchService instance for the current request.

    Args:
        session: Injected async database session.

    Returns:
        Configured SearchService instance.
    """
    from app.services.search_service import SearchService

    return SearchService(session)


async def get_parser_service(
    session: AsyncSession = Depends(get_db),
) -> "ParserService":  # type: ignore[name-defined]
    """Provide a ParserService instance for the current request.

    Args:
        session: Injected async database session.

    Returns:
        Configured ParserService instance.
    """
    from app.services.parser_service import ParserService

    return ParserService(session)


async def get_auth_service(
    session: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> "AuthService":  # type: ignore[name-defined]
    """Provide an AuthService instance for the current request.

    Args:
        session: Injected async database session.
        redis: Injected async Redis client.

    Returns:
        Configured AuthService instance.
    """
    from app.services.auth_service import AuthService

    return AuthService(session, redis)


def require_role(*allowed_roles: str) -> Callable[..., Any]:
    """Return a FastAPI dependency that enforces RBAC role membership.

    Usage::

        @router.get("/admin-only")
        async def endpoint(_: None = Depends(require_role("admin"))):
            ...

    Args:
        *allowed_roles: One or more role strings that are permitted.

    Returns:
        An async dependency function that raises HTTP 403 if the caller's
        role is not in ``allowed_roles``.
    """

    async def _check(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    ) -> None:
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            payload = jwt.decode(
                credentials.credentials,
                settings.secret_key,
                algorithms=[settings.jwt_algorithm],
            )
        except JWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token validation failed: {exc}",
            ) from exc

        role: str = payload.get("role", "")
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' is not permitted. Required: {list(allowed_roles)}.",
            )

    return _check
