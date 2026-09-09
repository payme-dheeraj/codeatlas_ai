"""Top-level API v1 router — aggregates all endpoint sub-routers."""

from fastapi import APIRouter

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

api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(users.router)
api_router.include_router(repositories.router)
api_router.include_router(parser.router)
api_router.include_router(search.router)
api_router.include_router(security.router)
api_router.include_router(documents.router)
api_router.include_router(diagrams.router)
api_router.include_router(admin.router)
api_router.include_router(health_score.router)
api_router.include_router(pr_review.router)
api_router.include_router(webhooks.router)
