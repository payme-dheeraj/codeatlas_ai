"""Chat / RAG conversation endpoints.

Routes:
  POST /chat/sessions                          — create a new session
  GET  /chat/sessions?repo_id=<uuid>           — list sessions for a repo
  GET  /chat/sessions/{session_id}/messages    — get all messages in a session
  GET  /chat/sessions/{session_id}/stream      — SSE stream a new message
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.logging import get_logger
from app.rag.graph import run_rag

logger = get_logger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

# ── Session & Message persistence with Redis + in-memory fallback ────────────
_sessions: dict[str, dict[str, Any]] = {}
_messages: dict[str, list[dict[str, Any]]] = {}

_executor = ThreadPoolExecutor(max_workers=4)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_redis_client():
    try:
        import redis.asyncio as aioredis
        from app.core.redis import get_redis_pool

        return aioredis.Redis(connection_pool=get_redis_pool())
    except Exception as exc:
        logger.warning("chat_redis_unavailable", error=str(exc))
        return None


async def _save_session(session: dict[str, Any]) -> None:
    _sessions[session["id"]] = session
    try:
        r = await _get_redis_client()
        if r:
            await r.set(f"chat:session:{session['id']}", json.dumps(session), ex=86400 * 7)
            if session.get("repo_id"):
                await r.sadd(f"chat:repo:{session['repo_id']}:sessions", session["id"])
    except Exception as exc:
        logger.debug("redis_save_session_fallback", error=str(exc))


async def _get_session(session_id: str) -> dict[str, Any] | None:
    if session_id in _sessions:
        return _sessions[session_id]
    try:
        r = await _get_redis_client()
        if r:
            raw = await r.get(f"chat:session:{session_id}")
            if raw:
                data = json.loads(raw)
                _sessions[session_id] = data
                return data
    except Exception as exc:
        logger.debug("redis_get_session_fallback", error=str(exc))
    return None


async def _list_sessions(repo_id: str = "") -> list[dict[str, Any]]:
    sessions_map: dict[str, dict[str, Any]] = dict(_sessions)
    try:
        r = await _get_redis_client()
        if r:
            if repo_id:
                session_ids = await r.smembers(f"chat:repo:{repo_id}:sessions")
            else:
                session_ids = [k.replace("chat:session:", "") for k in await r.keys("chat:session:*")]
            for sid in session_ids:
                if sid not in sessions_map:
                    raw = await r.get(f"chat:session:{sid}")
                    if raw:
                        data = json.loads(raw)
                        sessions_map[sid] = data
                        _sessions[sid] = data
    except Exception as exc:
        logger.debug("redis_list_sessions_fallback", error=str(exc))

    result = [s for s in sessions_map.values() if not repo_id or s.get("repo_id") == repo_id]
    result.sort(key=lambda s: s.get("created_at", ""), reverse=True)
    return result


async def _get_messages(session_id: str) -> list[dict[str, Any]]:
    if session_id in _messages and _messages[session_id]:
        return _messages[session_id]
    try:
        r = await _get_redis_client()
        if r:
            raw = await r.get(f"chat:messages:{session_id}")
            if raw:
                data = json.loads(raw)
                _messages[session_id] = data
                return data
    except Exception as exc:
        logger.debug("redis_get_messages_fallback", error=str(exc))
    return _messages.get(session_id, [])


async def _save_messages(session_id: str, msgs: list[dict[str, Any]]) -> None:
    _messages[session_id] = msgs
    try:
        r = await _get_redis_client()
        if r:
            await r.set(f"chat:messages:{session_id}", json.dumps(msgs), ex=86400 * 7)
    except Exception as exc:
        logger.debug("redis_save_messages_fallback", error=str(exc))


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/sessions", status_code=201)
async def create_session(body: dict[str, Any]):
    """Create a new chat session scoped to a repository."""
    repo_id = str(body.get("repo_id", ""))
    session_id = str(uuid.uuid4())
    session = {
        "id": session_id,
        "repo_id": repo_id,
        "title": "New conversation",
        "created_at": _now(),
    }
    await _save_session(session)
    await _save_messages(session_id, [])
    logger.info("chat_session_created", session_id=session_id, repo_id=repo_id)
    return session


@router.get("/sessions")
async def list_sessions(repo_id: str = Query(default="")):
    """Return all sessions for the given repo_id."""
    return await _list_sessions(repo_id)


@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str):
    """Return all messages for a session."""
    return await _get_messages(session_id)


@router.get("/sessions/{session_id}/stream")
async def stream_message(
    session_id: str,
    message: str = Query(...),
    token: str = Query(default=""),
):
    """Stream an SSE response for a new user message using the RAG pipeline."""

    async def event_generator():
        session = await _get_session(session_id)
        if not session:
            yield f"data: [DONE]\n\n"
            return

        repo_id = session.get("repo_id", "")

        # Persist user message
        user_msg: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "role": "user",
            "content": message,
            "citations": [],
            "created_at": _now(),
        }
        current_msgs = await _get_messages(session_id)
        current_msgs.append(user_msg)
        await _save_messages(session_id, current_msgs)

        # Update session title from first user message
        if len(current_msgs) == 1:
            session["title"] = message[:60]
            await _save_session(session)

        # Run RAG in thread pool (blocking call)
        loop = asyncio.get_event_loop()
        try:
            state = await loop.run_in_executor(
                _executor,
                lambda: run_rag(
                    message,
                    repo_ids=[repo_id] if repo_id else None,
                    llm_provider=settings.llm_provider,
                    llm_model=settings.anthropic_model
                    if settings.llm_provider == "anthropic"
                    else (
                        settings.openai_model
                        if settings.llm_provider == "openai"
                        else settings.ollama_model
                    ),
                ),
            )
        except Exception as exc:
            logger.error("rag_failed", error=str(exc))
            error_msg = f"Sorry, an error occurred: {exc}"
            yield f"data: {error_msg}\n\n"
            yield "data: [DONE]\n\n"
            return

        answer: str = state.get("answer") or "I could not generate an answer."
        context_chunks: list[dict] = state.get("context_chunks") or []

        # Build citations from context chunks
        citations = []
        seen: set[str] = set()
        for chunk in context_chunks[:5]:
            fp = chunk.get("file_path", "")
            if fp and fp not in seen:
                seen.add(fp)
                citations.append({
                    "file_path": fp,
                    "line_start": chunk.get("line_start"),
                    "line_end": chunk.get("line_end"),
                })

        # Stream the answer word-by-word for a typing effect
        words = answer.split(" ")
        for i, word in enumerate(words):
            chunk = word if i == len(words) - 1 else word + " "
            yield f"data: {chunk}\n\n"
            await asyncio.sleep(0.02)

        # Persist assistant message
        assistant_msg: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "role": "assistant",
            "content": answer,
            "citations": citations,
            "created_at": _now(),
        }
        latest_msgs = await _get_messages(session_id)
        latest_msgs.append(assistant_msg)
        await _save_messages(session_id, latest_msgs)

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
