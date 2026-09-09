"""Webhook management endpoints.

Routes:
  POST /repos/{repo_id}/webhooks           — create webhook
  GET  /repos/{repo_id}/webhooks           — list webhooks for repo
  GET  /repos/{repo_id}/webhooks/{wid}     — get webhook detail
  DELETE /repos/{repo_id}/webhooks/{wid}   — deactivate webhook
  GET  /repos/{repo_id}/webhooks/{wid}/deliveries — delivery history
  POST /repos/{repo_id}/webhooks/{wid}/test       — send a test ping
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id, get_db
from app.core.rbac import require_permission
from app.models.role import PERM_WEBHOOK_MANAGE
from app.models.webhook import WEBHOOK_EVENTS
from app.services.webhook_service import WebhookService

router = APIRouter(tags=["webhooks"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class WebhookCreateRequest(BaseModel):
    """Payload to create a webhook subscription.

    Attributes:
        url: Target HTTPS URL.
        events: List of event slugs to subscribe to.
        secret: Optional HMAC signing secret.
    """

    url: str = Field(..., description="Target HTTPS URL")
    events: list[str] = Field(..., description=f"Event slugs. Valid: {sorted(WEBHOOK_EVENTS)}")
    secret: str | None = Field(default=None, description="HMAC-SHA256 signing secret")


class WebhookResponse(BaseModel):
    """Webhook resource response."""

    id: uuid.UUID
    repo_id: uuid.UUID
    url: str
    events: list[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class WebhookDeliveryResponse(BaseModel):
    """Webhook delivery record."""

    id: uuid.UUID
    webhook_id: uuid.UUID
    event: str
    response_status: int | None
    success: bool
    duration_ms: int | None
    attempt: int
    delivered_at: datetime

    model_config = {"from_attributes": True}


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/repos/{repo_id}/webhooks",
    response_model=WebhookResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a webhook subscription",
    dependencies=[Depends(require_permission(PERM_WEBHOOK_MANAGE))],
)
async def create_webhook(
    repo_id: uuid.UUID,
    body: WebhookCreateRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> WebhookResponse:
    """Create a new outbound webhook for a repository.

    Args:
        repo_id: UUID of the repository.
        body: Webhook configuration.
        user_id: Owner user UUID.
        session: Async DB session.

    Returns:
        Created WebhookResponse.
    """
    invalid = set(body.events) - WEBHOOK_EVENTS
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid events: {sorted(invalid)}. Valid: {sorted(WEBHOOK_EVENTS)}",
        )
    svc = WebhookService(session)
    webhook = await svc.create(repo_id, user_id, body.url, body.events, secret=body.secret)
    return WebhookResponse.model_validate(webhook)


@router.get(
    "/repos/{repo_id}/webhooks",
    response_model=list[WebhookResponse],
    summary="List webhooks for a repository",
    dependencies=[Depends(require_permission(PERM_WEBHOOK_MANAGE))],
)
async def list_webhooks(
    repo_id: uuid.UUID,
    _: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> list[WebhookResponse]:
    """Return all active webhooks for a repository.

    Args:
        repo_id: UUID of the repository.
        _: Authenticated user.
        session: Async DB session.

    Returns:
        List of WebhookResponse.
    """
    svc = WebhookService(session)
    webhooks = await svc.list_for_repo(repo_id)
    return [WebhookResponse.model_validate(w) for w in webhooks]


@router.get(
    "/repos/{repo_id}/webhooks/{webhook_id}",
    response_model=WebhookResponse,
    summary="Get a webhook by ID",
    dependencies=[Depends(require_permission(PERM_WEBHOOK_MANAGE))],
)
async def get_webhook(
    repo_id: uuid.UUID,
    webhook_id: uuid.UUID,
    _: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> WebhookResponse:
    """Fetch a webhook by UUID.

    Args:
        repo_id: Repository UUID.
        webhook_id: Webhook UUID.
        _: Authenticated user.
        session: Async DB session.

    Returns:
        WebhookResponse.

    Raises:
        HTTPException 404: If the webhook does not exist.
    """
    svc = WebhookService(session)
    webhook = await svc.get(webhook_id)
    if webhook is None or webhook.repo_id != repo_id:
        raise HTTPException(status_code=404, detail=f"Webhook '{webhook_id}' not found.")
    return WebhookResponse.model_validate(webhook)


@router.delete(
    "/repos/{repo_id}/webhooks/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deactivate (soft-delete) a webhook",
    dependencies=[Depends(require_permission(PERM_WEBHOOK_MANAGE))],
)
async def deactivate_webhook(
    repo_id: uuid.UUID,
    webhook_id: uuid.UUID,
    _: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Deactivate a webhook subscription.

    Args:
        repo_id: Repository UUID.
        webhook_id: Webhook UUID.
        _: Authenticated user.
        session: Async DB session.

    Raises:
        HTTPException 404: If the webhook does not exist.
    """
    svc = WebhookService(session)
    webhook = await svc.get(webhook_id)
    if webhook is None or webhook.repo_id != repo_id:
        raise HTTPException(status_code=404, detail=f"Webhook '{webhook_id}' not found.")
    await svc.deactivate(webhook_id)


@router.get(
    "/repos/{repo_id}/webhooks/{webhook_id}/deliveries",
    response_model=list[WebhookDeliveryResponse],
    summary="Get delivery history for a webhook",
    dependencies=[Depends(require_permission(PERM_WEBHOOK_MANAGE))],
)
async def list_deliveries(
    repo_id: uuid.UUID,
    webhook_id: uuid.UUID,
    _: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> list[WebhookDeliveryResponse]:
    """Return recent delivery records for a webhook.

    Args:
        repo_id: Repository UUID.
        webhook_id: Webhook UUID.
        _: Authenticated user.
        session: Async DB session.

    Returns:
        List of WebhookDeliveryResponse.

    Raises:
        HTTPException 404: If the webhook does not exist.
    """
    svc = WebhookService(session)
    webhook = await svc.get(webhook_id)
    if webhook is None or webhook.repo_id != repo_id:
        raise HTTPException(status_code=404, detail=f"Webhook '{webhook_id}' not found.")
    deliveries = await svc.deliveries(webhook_id)
    return [WebhookDeliveryResponse.model_validate(d) for d in deliveries]


@router.post(
    "/repos/{repo_id}/webhooks/{webhook_id}/test",
    summary="Send a test ping to a webhook",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission(PERM_WEBHOOK_MANAGE))],
)
async def test_webhook(
    repo_id: uuid.UUID,
    webhook_id: uuid.UUID,
    _: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Send a test ping event to verify the webhook URL is reachable.

    Args:
        repo_id: Repository UUID.
        webhook_id: Webhook UUID.
        _: Authenticated user.
        session: Async DB session.

    Returns:
        Delivery result dict.

    Raises:
        HTTPException 404: If the webhook does not exist.
    """
    svc = WebhookService(session)
    webhook = await svc.get(webhook_id)
    if webhook is None or webhook.repo_id != repo_id:
        raise HTTPException(status_code=404, detail=f"Webhook '{webhook_id}' not found.")

    results = await svc.dispatch_event(
        repo_id,
        "scan.complete",
        {"test": True, "message": "This is a CodeAtlas test ping."},
    )
    return {"delivered": len(results), "results": results}
