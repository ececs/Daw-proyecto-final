"""AI agent REST API.

FastAPI routes that drive the LangGraph agent: streaming chat over SSE,
chat history retrieval from the Postgres checkpointer, AI status and
metrics endpoints, and the feedback submission endpoint used by the
thumbs-up/down UI.
"""

import logging
import json
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.messages import HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentUser, DB
from app.ai.agent import build_agent
from app.ai.checkpoint import get_checkpointer
from app.ai import observability
from app.models.ai_run import AIRun
from app.schemas.ai_metrics import AIFeedbackCreate
from app.services import ai_metrics_service, ticket_service

router = APIRouter(prefix="/ai", tags=["AI Agent"])

_SPANISH_HINTS = {
    "el", "la", "los", "las", "un", "una", "para", "porque", "que", "como",
    "con", "sin", "hola", "gracias", "problema", "cambio", "quiero", "puedes",
    "necesito", "tengo", "esto", "esta", "es", "en", "ticket", "prioridad",
}


class ChatMessage(BaseModel):
    """Single message in a chat request (`role` is `"user"` or `"assistant"`)."""
    role: str
    content: str


class ChatRequest(BaseModel):
    """Body of `POST /ai/chat`.

    Carries the user's prompt history together with optional UI context
    (current ticket, multi-selected tickets) and the desired provider
    override.
    """
    messages: List[ChatMessage]
    thread_id: Optional[str] = None
    current_ticket_id: Optional[str] = None
    selected_ticket_ids: Optional[List[str]] = None
    preferred_provider: Optional[str] = None


def _infer_chat_language(messages: List[ChatMessage]) -> str:
    """Infer the dominant language of the current user conversation.

    Returns `"Spanish"` or `"English"` so the runtime context can pin the
    assistant language even when the model decides to default to English.
    """
    text = "\n".join(msg.content for msg in messages if msg.role == "user" and msg.content).lower()
    if not text:
        return "English"
    if re.search(r"[áéíóúñ¿¡]", text):
        return "Spanish"
    tokens = re.findall(r"[a-zA-Z]+", text)
    spanish_hits = sum(1 for token in tokens if token in _SPANISH_HINTS)
    return "Spanish" if spanish_hits >= 2 else "English"


async def _agent_sse_stream(
    agent,
    initial_state,
    config: dict,
    thread_id: str,
    tracker: ai_metrics_service.AIRunTracker,
    ai_run_id: str,
):
    """Translate the LangGraph event stream into SSE frames.

    Forwards model tokens, `tool_start` / `tool_call` boundaries and
    error events to the browser. Two special tool outputs are intercepted
    here and turned into UI events instead of plain tool results:

    - `__DELETE_REQUESTED__:...` → `confirmation_required` (author asked
      to delete their own ticket; the frontend shows a confirm dialog).
    - `__DELETE_REQUEST_OFFER__:...` → `deletion_request_offer` (a non-
      author asked to delete; the frontend offers to *notify* the author
      instead).

    Yields:
        str: Lines in the `data: <json>\\n\\n` SSE format.
    """
    v_logger = logging.getLogger("uvicorn.error")
    yield f"data: {json.dumps({'type': 'session', 'thread_id': thread_id, 'ai_run_id': ai_run_id})}\n\n"
    yield f"data: {json.dumps({'type': 'token', 'content': ' '})}\n\n"

    try:
        has_content = False
        active_model = "IA"
        debug_prefix_sent = False

        async for event in agent.astream_events(initial_state, version="v2", config=config):
            kind = event["event"]

            if kind == "on_chat_model_start":
                m_name = event.get("name", "")
                tracker.register_model(m_name)
                if "Google" in m_name:
                    active_model = "Gemini"
                elif "OpenAI" in m_name:
                    active_model = "GPT"
                v_logger.info("AI Model Starting: %s (%s)", m_name, active_model)

            elif kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                if chunk and hasattr(chunk, "content") and chunk.content:
                    has_content = True
                    content = chunk.content
                    if not debug_prefix_sent:
                        content = f"{active_model}: " + content
                        debug_prefix_sent = True
                    tracker.append_output(content)
                    yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"

            elif kind == "on_tool_start":
                yield f"data: {json.dumps({'type': 'tool_start', 'name': event.get('name', '')})}\n\n"

            elif kind == "on_tool_end":
                observability.increment_action()
                tracker.add_tool_action()
                tool_name = event.get("name", "")
                raw_output = event.get("data", {}).get("output", "")
                tool_output = str(raw_output.content) if hasattr(raw_output, "content") else str(raw_output)

                if tool_output.startswith("__DELETE_REQUESTED__:"):
                    parts = tool_output.split(":", 2)
                    t_id = parts[1] if len(parts) > 1 else ""
                    t_title = parts[2] if len(parts) > 2 else "este ticket"
                    yield f"data: {json.dumps({'type': 'confirmation_required', 'ticket_id': t_id, 'ticket_title': t_title})}\n\n"
                elif tool_output.startswith("__DELETE_REQUEST_OFFER__:"):
                    parts = tool_output.split(":", 2)
                    t_id = parts[1] if len(parts) > 1 else ""
                    t_title = parts[2] if len(parts) > 2 else "este ticket"
                    yield f"data: {json.dumps({'type': 'deletion_request_offer', 'ticket_id': t_id, 'ticket_title': t_title})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'tool_call', 'name': tool_name, 'result': tool_output})}\n\n"

        if not has_content:
            v_logger.warning("AI Stream: no content for thread %s", thread_id)
            yield f"data: {json.dumps({'type': 'token', 'content': '*(Sistema: Los modelos de IA no han respondido. Por favor, intenta de nuevo.)*'})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    except Exception as e:
        error_msg = str(e)
        v_logger.error("SSE stream error: %s", error_msg, exc_info=True)
        tracker.error_message = error_msg
        friendly = _make_friendly_error(error_msg)
        yield f"data: {json.dumps({'type': 'error', 'content': friendly})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"


def _make_friendly_error(error_msg: str) -> str:
    """Map a raw provider error message into a human-readable English line.

    Falls back to the original message when no rule matches.
    """
    if "429" in error_msg or "quota" in error_msg.lower():
        return "*(System: AI usage limit reached. Please wait a few seconds.)*"
    if "api_key" in error_msg.lower() or "401" in error_msg:
        return "*(System: AI API key configuration error.)*"
    return error_msg


async def _resolve_ticket_id_for_chat(
    request: ChatRequest, db: AsyncSession
) -> uuid.UUID | None:
    """Pick a single ticket id out of the chat-request UI context.

    Prefers `current_ticket_id`; falls back to `selected_ticket_ids`
    only when exactly one ticket is selected. Returns `None` when no
    unambiguous target can be derived.
    """
    from app.models.ticket import Ticket

    async def resolve_ref(ref: str) -> uuid.UUID | None:
        try:
            number = int(ref)
            result = await db.execute(
                select(Ticket).where(Ticket.ticket_number == number)
            )
            row = result.scalar_one_or_none()
            if row:
                return row.id
        except (ValueError, Exception):
            pass
        try:
            uid = uuid.UUID(ref)
            exists = await db.get(Ticket, uid)
            return uid if exists is not None else None
        except ValueError:
            return None

    if request.current_ticket_id:
        result = await resolve_ref(request.current_ticket_id)
        if result:
            return result
    if request.selected_ticket_ids and len(request.selected_ticket_ids) == 1:
        return await resolve_ref(request.selected_ticket_ids[0])
    return None


@router.get("/history/{thread_id}", summary="Get chat history for a thread")
async def get_chat_history(thread_id: str):
    """Return the persisted chat messages for a given thread.

    Reads the LangGraph checkpointer (PostgreSQL) so the frontend can
    rehydrate the conversation after a page reload without storing
    history in `localStorage`.

    Returns:
        dict: `{"messages": [{"role": str, "content": str}, ...]}`.
    """
    checkpointer = get_checkpointer()
    if not checkpointer:
        return {"messages": []}

    config = {"configurable": {"thread_id": thread_id}}
    state = await checkpointer.aget(config)

    if not state or "messages" not in state.values:
        return {"messages": []}

    history = []
    for msg in state.values["messages"]:
        role = "user" if msg.type == "human" else "assistant"
        if msg.type in ["human", "ai"]:
            history.append({"role": role, "content": msg.content})

    return {"messages": history}


@router.post("/chat", summary="Stream an AI chat response (SSE)")
async def chat(
    request: ChatRequest,
    db: DB,
    current_user: CurrentUser,
):
    """Run the agent on the user's prompt and stream the answer as SSE.

    Pipeline per request:

    1. Build an `AIRunTracker` and an `AIRun` row so latency, cost and
       provider/model are recorded even if the client disconnects.
    2. Fetch the optional ticket context from the request body and
       compose the extra system context the agent will see.
    3. Compile a fresh `build_agent(...)` graph bound to this session.
    4. Stream LangGraph events through `_agent_sse_stream`; finalise the
       `AIRun` in a `finally` block.
    """
    checkpointer = get_checkpointer()
    thread_id = request.thread_id or str(current_user.id)
    ai_run: AIRun | None = None

    observability.increment_chat()
    v_logger = logging.getLogger("uvicorn.error")
    v_logger.info("AI Session: thread_id=%s", thread_id)

    context_parts = []

    if request.current_ticket_id:
        try:
            from app.services.ticket_service import get_ticket
            ticket_data = await get_ticket(db, uuid.UUID(request.current_ticket_id))
            if ticket_data:
                context_parts.append(
                    f"USER IS CURRENTLY VIEWING THIS TICKET (USE THIS FULL ID FOR ACTIONS):\n"
                    f"FULL_ID: {str(ticket_data.id)}\n"
                    f"Title: {ticket_data.title}\n"
                    f"Status: {ticket_data.status.value}\n"
                    f"Priority: {ticket_data.priority.value}\n"
                    f"Description: {ticket_data.description or 'No description'}"
                )
        except Exception as e:
            v_logger.warning("AI Context: failed to fetch ticket: %s", e)

    if request.selected_ticket_ids:
        try:
            from app.models.ticket import Ticket
            from sqlalchemy import select
            other_ids = [
                uuid.UUID(tid) for tid in request.selected_ticket_ids
                if tid != request.current_ticket_id
            ]
            if other_ids:
                from sqlalchemy import select as sa_select
                res = await db.execute(sa_select(Ticket).where(Ticket.id.in_(other_ids)))
                selected = res.scalars().all()
                if selected:
                    lines = "USER HAS SELECTED THESE TICKETS (USE THESE FULL IDs FOR ACTIONS):\n"
                    for t in selected:
                        lines += f"- Title: {t.title} | Status: {t.status.value} | FULL_ID: {str(t.id)}\n"
                    context_parts.append(lines)
        except Exception as e:
            v_logger.warning("AI Context: failed to fetch selected tickets: %s", e)

    inferred_language = _infer_chat_language(request.messages)
    context_parts.insert(
        0,
        f"CURRENT USER LANGUAGE: {inferred_language}. "
        f"Reply in {inferred_language} and keep using it unless the user explicitly switches language."
    )
    extra_context = "\n\n" + "\n\n---\n\n".join(context_parts) if context_parts else ""
    input_tokens = sum(ai_metrics_service.estimate_tokens(msg.content) for msg in request.messages)
    tracker = ai_metrics_service.AIRunTracker(
        surface="chat",
        user_id=current_user.id,
        ticket_id=await _resolve_ticket_id_for_chat(request, db),
        thread_id=thread_id,
        primary_provider=ai_metrics_service.configured_primary_signature()[0] if (request.preferred_provider or "auto") == "auto" else request.preferred_provider,
        primary_model="gpt-4o-mini" if request.preferred_provider == "openai" else ("gemini-2.5-flash" if request.preferred_provider == "google" else ai_metrics_service.configured_primary_signature()[1]),
        input_tokens=input_tokens,
    )

    try:
        ai_run = await ai_metrics_service.create_ai_run(
            db,
            user_id=current_user.id,
            surface="chat",
            ticket_id=tracker.ticket_id,
            thread_id=thread_id,
            estimated_input_tokens=input_tokens,
        )
        tracker.ai_run_id = ai_run.id
        agent = build_agent(
            db,
            current_user,
            system_context=extra_context,
            metrics_tracker=tracker,
            preferred_provider=request.preferred_provider,
            current_language=inferred_language,
        )
    except Exception as e:
        error_msg = str(e)
        v_logger.error("AI Initialization Failed: %s", error_msg, exc_info=True)
        tracker.error_message = error_msg
        if ai_run is not None:
            await ai_metrics_service.finalize_ai_run(
                db,
                ai_run,
                tracker,
                success=False,
                error_message=error_msg,
            )
        else:
            observability.record_error(error_msg, tracker.surface)

        async def error_generator():
            yield f"data: {json.dumps({'type': 'error', 'content': f'*(Configuration Error: {error_msg})*'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(error_generator(), media_type="text/event-stream")

    if checkpointer and thread_id:
        initial_state = {
            "messages": [HumanMessage(content=request.messages[-1].content)],
            "remaining_steps": 40,
        }
    else:
        initial_state = {
            "messages": [
                {"role": msg.role, "content": msg.content}
                for msg in request.messages
            ],
            "remaining_steps": 40,
        }

    config = {"configurable": {"thread_id": thread_id}}

    if checkpointer:
        state = await agent.aget_state(config)
        history_count = len(state.values.get("messages", [])) if state.values else 0
        v_logger.info("Memory Check: Thread %s has %d messages", thread_id, history_count)

    async def event_stream():
        try:
            async for chunk in _agent_sse_stream(agent, initial_state, config, thread_id, tracker, str(ai_run.id)):
                yield chunk
        finally:
            await ai_metrics_service.finalize_ai_run(
                db,
                ai_run,
                tracker,
                success=tracker.error_message is None,
                error_message=tracker.error_message,
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/status", summary="AI assistant operational status")
async def get_ai_status(
    current_user: CurrentUser,
    db: DB,
    since: str | None = None,
):
    """Return the live AI status merged with per-session metrics.

    The base payload comes from the in-memory `observability` module
    (provider, model, fallback availability); when `since` is provided,
    per-user database statistics from that point in time are merged on
    top.
    """
    base = observability.get_status()
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=timezone.utc)
            session_stats = await ai_metrics_service.get_session_stats(
                db, current_user.id, since_dt
            )
            base.update(session_stats)
            base.setdefault("last_rag_source", "none")
        except ValueError:
            pass
    return base


@router.get("/stats", summary="Global AI usage dashboard")
async def get_ai_stats(db: DB, current_user: CurrentUser):
    """Return the global AI metrics summary used by the analytics dashboard."""
    return await ai_metrics_service.get_stats_summary(db)


@router.get("/stats/tickets/{ticket_ref}", summary="AI metrics for a single ticket")
async def get_ticket_ai_stats(ticket_ref: str, db: DB, current_user: CurrentUser):
    """Return AI usage metrics scoped to a single ticket."""
    ticket = await ticket_service.resolve_ticket(db, ticket_ref)
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    try:
        return await ai_metrics_service.get_ticket_stats(db, ticket.id)
    except Exception:
        logging.getLogger("uvicorn.error").exception(
            "get_ticket_ai_stats failed for ticket %s (ref=%s)", ticket.id, ticket_ref
        )
        raise


@router.post("/feedback", summary="Submit thumbs-up/down feedback for an AI run")
async def create_ai_feedback(payload: AIFeedbackCreate, db: DB, current_user: CurrentUser):
    """Upsert the current user's feedback on a previous `AIRun`.

    Raises:
        HTTPException: **404** if the `ai_run_id` does not exist.
    """
    run = await db.get(AIRun, payload.ai_run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI run not found")
    feedback = await ai_metrics_service.create_feedback(
        db,
        ai_run_id=payload.ai_run_id,
        user_id=current_user.id,
        helped=payload.helped,
        label=payload.label,
        notes=payload.notes,
    )
    return {
        "id": str(feedback.id),
        "ai_run_id": str(feedback.ai_run_id),
        "user_id": str(feedback.user_id) if feedback.user_id else None,
        "helped": feedback.helped,
        "label": feedback.label,
        "notes": feedback.notes,
        "created_at": feedback.created_at.isoformat(),
    }
