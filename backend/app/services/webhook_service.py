"""Webhook service — manage subscriptions and deliver events."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.webhook import Webhook, WebhookDelivery

logger = get_logger(__name__)


class WebhookService:
    """Async service for webhook lifecycle and event delivery.

    Attributes:
        _session: Async SQLAlchemy session.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── CRUD ──────────────────────────────────────────────────────────────────

    async def create(
        self,
        repo_id: uuid.UUID,
        user_id: uuid.UUID,
        url: str,
        events: list[str],
        *,
        secret: str | None = None,
    ) -> Webhook:
        """Create a new webhook subscription.

        Args:
            repo_id: Repository UUID.
            user_id: Owner user UUID.
            url: Target HTTPS URL.
            events: List of event slugs to subscribe to.
            secret: Optional HMAC signing secret.

        Returns:
            Persisted Webhook instance.
        """
        webhook = Webhook(
            repo_id=repo_id,
            user_id=user_id,
            url=url,
            events=events,
            secret=secret,
            is_active=True,
        )
        self._session.add(webhook)
        await self._session.commit()
        await self._session.refresh(webhook)
        logger.info("webhook_created", webhook_id=str(webhook.id), url=url)
        return webhook

    async def list_for_repo(self, repo_id: uuid.UUID) -> list[Webhook]:
        """Return all active webhooks for a repository.

        Args:
            repo_id: Repository UUID.

        Returns:
            List of active Webhook instances.
        """
        result = await self._session.execute(
            select(Webhook).where(
                Webhook.repo_id == repo_id, Webhook.is_active.is_(True)
            )
        )
        return list(result.scalars().all())

    async def get(self, webhook_id: uuid.UUID) -> Webhook | None:
        """Fetch a webhook by UUID.

        Args:
            webhook_id: Webhook UUID.

        Returns:
            Webhook or None.
        """
        result = await self._session.execute(
            select(Webhook).where(Webhook.id == webhook_id)
        )
        return result.scalar_one_or_none()

    async def deactivate(self, webhook_id: uuid.UUID) -> None:
        """Deactivate a webhook (soft delete).

        Args:
            webhook_id: Webhook UUID.
        """
        await self._session.execute(
            update(Webhook).where(Webhook.id == webhook_id).values(is_active=False)
        )
        await self._session.commit()

    async def deliveries(
        self, webhook_id: uuid.UUID, *, limit: int = 50
    ) -> list[WebhookDelivery]:
        """Return recent delivery records for a webhook.

        Args:
            webhook_id: Webhook UUID.
            limit: Maximum records to return.

        Returns:
            List of WebhookDelivery records, newest first.
        """
        from sqlalchemy import desc
        result = await self._session.execute(
            select(WebhookDelivery)
            .where(WebhookDelivery.webhook_id == webhook_id)
            .order_by(desc(WebhookDelivery.delivered_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    # ── Event delivery ─────────────────────────────────────────────────────────

    async def dispatch_event(
        self,
        repo_id: uuid.UUID,
        event: str,
        payload: dict[str, Any],
    ) -> list[dict]:
        """Fire an event to all matching active webhooks for a repository.

        Args:
            repo_id: Repository UUID.
            event: Event slug (e.g. scan.complete).
            payload: Event payload dict.

        Returns:
            List of delivery result dicts.
        """
        result = await self._session.execute(
            select(Webhook).where(
                Webhook.repo_id == repo_id,
                Webhook.is_active.is_(True),
            )
        )
        webhooks = list(result.scalars().all())

        results = []
        for webhook in webhooks:
            if event not in (webhook.events or []):
                continue
            delivery_result = await self._deliver(webhook, event, payload)
            results.append(delivery_result)

        return results

    async def _deliver(
        self,
        webhook: Webhook,
        event: str,
        payload: dict[str, Any],
        *,
        attempt: int = 1,
    ) -> dict:
        """Deliver a single webhook event.

        Signs the payload with HMAC-SHA256 if a secret is configured.

        Args:
            webhook: Webhook instance.
            event: Event slug.
            payload: Payload dict.
            attempt: Attempt number.

        Returns:
            Delivery result dict.
        """
        full_payload = {
            "event": event,
            "webhook_id": str(webhook.id),
            "repo_id": str(webhook.repo_id),
            "delivered_at": datetime.now(UTC).isoformat(),
            "data": payload,
        }
        body = json.dumps(full_payload, default=str)
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "X-CodeAtlas-Event": event,
            "X-CodeAtlas-Delivery": str(uuid.uuid4()),
        }

        if webhook.secret:
            sig = hmac.new(
                webhook.secret.encode(), body.encode(), hashlib.sha256
            ).hexdigest()
            headers["X-CodeAtlas-Signature-256"] = f"sha256={sig}"

        start = time.monotonic()
        response_status = None
        response_body = ""
        success = False

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(webhook.url, content=body, headers=headers)
            response_status = resp.status_code
            response_body = resp.text[:2000]
            success = 200 <= response_status < 300
            logger.info("webhook_delivered", url=webhook.url, status=response_status)

        except Exception as exc:
            response_body = str(exc)[:2000]
            logger.warning("webhook_delivery_failed", url=webhook.url, error=str(exc))

        duration_ms = int((time.monotonic() - start) * 1000)

        delivery = WebhookDelivery(
            webhook_id=webhook.id,
            event=event,
            payload=full_payload,
            response_status=response_status,
            response_body=response_body,
            duration_ms=duration_ms,
            success=success,
            attempt=attempt,
        )
        self._session.add(delivery)
        await self._session.commit()

        return {
            "webhook_id": str(webhook.id),
            "event": event,
            "url": webhook.url,
            "status": response_status,
            "success": success,
            "duration_ms": duration_ms,
        }
