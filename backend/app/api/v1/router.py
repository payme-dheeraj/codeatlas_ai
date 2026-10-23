"""Top-level API v1 router — aggregates all endpoint sub-routers."""

from fastapi import APIRouter, Depends

from app.api.deps import require_authenticated
from app.api.v1.endpoints import (
    admin,
    auth,
    chat,
    diagrams,
    documents,
    health_score,
    parser,
    pr_review,
    repositories,
    search,
    security,
    users,
    webhooks,
)

api_router = APIRouter(prefix="/api/v1")

# Public: login / register / refresh live here (per-route auth where needed).
api_router.include_router(auth.router)

# Everything else sits behind the authentication gate (see AUTH_REQUIRED).
_protected = [Depends(require_authenticated)]
for _router in (
    chat.router,
    users.router,
    repositories.router,
    parser.router,
    search.router,
    security.router,
    documents.router,
    diagrams.router,
    admin.router,
    health_score.router,
    pr_review.router,
    webhooks.router,
):
    api_router.include_router(_router, dependencies=_protected)
